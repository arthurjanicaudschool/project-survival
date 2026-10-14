"""Atomic unit of work. PostgreSQL in live mode, SQLite only for demo/tests."""

import json
import os
import sqlite3
import threading
from datetime import timedelta
from contextlib import contextmanager
from pathlib import Path
import psycopg
from psycopg.types.json import Jsonb
from .models import utcnow

_DEMO_LEASES = {}

AUDIT_TABLES = {
    "cycles",
    "market_snapshots",
    "agent_decisions",
    "simulated_orders",
    "simulated_fills",
    "ledger_entries",
    "portfolio_snapshots",
    "system_events",
    "final_reports",
}


class Store:
    def __init__(self, url=None, demo_path=None):
        self.demo = demo_path is not None
        if self.demo:
            Path(demo_path).parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(demo_path, timeout=2, isolation_level=None)
            self.db.execute(
                "create table if not exists experiments(id text primary key,state text not null)"
            )
            self.db.execute(
                "create table if not exists audit(id text primary key,kind text,payload text)"
            )
            self.db.execute(
                "create table if not exists local_tasks(id text primary key,payload text)"
            )
        else:
            self.url = url or os.environ["DATABASE_URL"]
            self.db = psycopg.connect(self.url, autocommit=True, connect_timeout=15)

    def close(self):
        self.db.close()

    @contextmanager
    def lease(self, eid):
        """Session lock without keeping a financial transaction open during HTTP."""
        if self.demo:
            path = self.db.execute("pragma database_list").fetchone()[2]
            lock = _DEMO_LEASES.setdefault((path, eid), threading.Lock())
            if not lock.acquire(False):
                raise RuntimeError("Another cycle holds the experiment lease")
            try:
                yield self
            finally:
                lock.release()
        else:
            if not self.db.execute(
                "select pg_try_advisory_lock(hashtextextended(%s,0))", (eid,)
            ).fetchone()[0]:
                raise RuntimeError("Another cycle holds the experiment lease")
            try:
                yield self
            finally:
                self.db.execute(
                    "select pg_advisory_unlock(hashtextextended(%s,0))", (eid,)
                )

    def task_get(self, identifier):
        if self.demo:
            row = self.db.execute(
                "select payload from local_tasks where id=?", (identifier,)
            ).fetchone()
            return json.loads(row[0]) if row else None
        row = self.db.execute(
            "select payload from analysis_sessions where id=%s", (identifier,)
        ).fetchone()
        return row[0] if row else None

    def audit_exists(self, table, identifier):
        if table not in AUDIT_TABLES:
            raise ValueError("Unknown audit table")
        if self.demo:
            return bool(
                self.db.execute(
                    "select 1 from audit where id=?", (table + ":" + identifier,)
                ).fetchone()
            )
        from psycopg import sql

        return bool(
            self.db.execute(
                sql.SQL("select 1 from {} where id=%s").format(sql.Identifier(table)),
                (identifier,),
            ).fetchone()
        )

    def task_save(self, identifier, eid, aid, payload):
        if self.demo:
            self.db.execute(
                "insert into local_tasks values(?,?) on conflict(id) do update set payload=excluded.payload",
                (identifier, json.dumps(payload)),
            )
        else:
            self.db.execute(
                "insert into analysis_sessions(id,experiment_id,agent_id,status,created_at,payload) values(%s,%s,%s,%s,%s,%s) on conflict(id) do update set status=excluded.status,updated_at=now(),payload=excluded.payload",
                (
                    identifier,
                    eid,
                    aid,
                    payload["status"],
                    payload["created_at"],
                    Jsonb(payload),
                ),
            )

    def cache_get(self, key):
        if self.demo:
            return None
        row = self.db.execute(
            "select payload from external_cache where key=%s and expires_at>now()",
            (key,),
        ).fetchone()
        return row[0] if row else None

    def cache_put(self, key, payload, ttl):
        if not self.demo:
            self.db.execute(
                "insert into external_cache values(%s,%s,%s) on conflict(key) do update set expires_at=excluded.expires_at,payload=excluded.payload",
                (key, utcnow() + timedelta(seconds=ttl), Jsonb(payload)),
            )

    def meter_reserve(self, eid, aid, estimate):
        if self.demo:
            return None
        from decimal import Decimal as D
        from uuid import uuid4
        from .agents import SETTINGS

        identifier = str(uuid4())
        with psycopg.connect(self.url, connect_timeout=15) as db:
            db.execute("select pg_advisory_xact_lock(hashtextextended(%s,4))", (eid,))
            total, today = db.execute(
                "select coalesce(sum(estimated_eur),0),coalesce(sum(estimated_eur) filter(where created_at >= date_trunc('day',now() at time zone 'UTC') at time zone 'UTC'),0) from llm_meter where experiment_id=%s",
                (eid,),
            ).fetchone()
            if total + estimate > D(
                SETTINGS["analysis_budget_eur"]
            ) or today + estimate > D(SETTINGS["analysis_daily_budget_eur"]):
                raise ValueError("AZURE_ESTIMATED_BUDGET_REACHED")
            db.execute(
                "insert into llm_meter(id,experiment_id,agent_id,status,estimated_eur,payload) values(%s,%s,%s,'RESERVED',%s,'{}')",
                (identifier, eid, aid, estimate),
            )
        return identifier

    def meter_finish(self, identifier, usage, estimated):
        if identifier:
            with psycopg.connect(self.url, connect_timeout=15) as db:
                db.execute(
                    "update llm_meter set status='MEASURED',estimated_eur=%s,payload=%s where id=%s",
                    (estimated, Jsonb(usage), identifier),
                )

    def meter_summary(self, eid):
        if self.demo:
            return {"mode": "demo", "estimated_eur": "0"}
        from .agents import SETTINGS

        total, today, uncertain = self.db.execute(
            "select coalesce(sum(estimated_eur),0),coalesce(sum(estimated_eur) filter(where created_at>=date_trunc('day',now() at time zone 'UTC') at time zone 'UTC'),0),count(*) filter(where status='RESERVED') from llm_meter where experiment_id=%s",
            (eid,),
        ).fetchone()
        return {
            "estimated_eur": str(total),
            "today_estimated_eur": str(today),
            "total_limit_eur": SETTINGS["analysis_budget_eur"],
            "daily_limit_eur": SETTINGS["analysis_daily_budget_eur"],
            "uncertain_requests_reserved": uncertain,
            "method": "Conservative user-supplied long Data Zone rates incl. highest cache write. Reservations survive failures; historical baseline is estimated. Actual Azure billing is authoritative.",
        }

    def historical_markets(self, eid, cutoff, max_age):
        if self.demo:
            rows = [
                json.loads(r[0])
                for r in self.db.execute(
                    "select payload from audit where kind='market_snapshots'"
                )
            ]
            rows = [
                r
                for r in rows
                if r.get("experiment_id") == eid
                and str(r["created_at"]) <= cutoff.isoformat()
            ]
        else:
            rows = [
                {"created_at": str(r[0]), "payload": r[1]}
                for r in self.db.execute(
                    "select created_at,payload from market_snapshots where experiment_id=%s and created_at<=%s order by created_at",
                    (eid, cutoff),
                )
            ]
        from .models import Market

        result = {}
        for r in rows:
            m = Market.model_validate(r["payload"])
            m.books = {
                o: b
                for o, b in m.books.items()
                if 0 <= (cutoff - b.observed_at).total_seconds() <= max_age
            }
            if m.books or m.resolved and m.resolved_at and m.resolved_at <= cutoff:
                result[m.id] = m
        return result

    def reserve_llm(self, eid, aid, cycle_id, now, limit):
        if self.demo:
            return True
        # Independent committed quota journal survives cycle rollbacks/crashes.
        with psycopg.connect(self.url, connect_timeout=15) as quota:
            quota.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s,1))",
                (f"{eid}:{aid}:llm",),
            )
            count = quota.execute(
                "select count(*) from llm_attempts where experiment_id=%s and agent_id=%s and utc_day=%s",
                (eid, aid, now.date()),
            ).fetchone()[0]
            if count >= limit:
                return False
            result = quota.execute(
                "insert into llm_attempts(id,experiment_id,agent_id,utc_day,created_at) values(%s,%s,%s,%s,%s) on conflict(id) do nothing returning id",
                (f"{eid}:{cycle_id}:{aid}", eid, aid, now.date(), now),
            ).fetchone()
            return bool(result)

    def quota_usage(self):
        if self.demo:
            return {"mode": "demo", "database_bytes": 0}
        size = self.db.execute(
            "select pg_database_size(current_database())"
        ).fetchone()[0]
        projection = self.db.execute(
            "select coalesce(sum(pg_column_size(payload)),0) from dashboard_states"
        ).fetchone()[0]
        return {
            "database_bytes": size,
            "dashboard_bytes": projection,
            "free_database_limit_bytes": 500000000,
        }

    def assert_wallet(self, eid, aid, wallet):
        from decimal import Decimal as D

        if self.demo:
            entries = [
                json.loads(r[0])
                for r in self.db.execute(
                    "select payload from audit where kind='ledger_entries'"
                )
            ]
            cash = sum(
                (
                    D(r["amount"])
                    for r in entries
                    if r["experiment_id"] == eid and r["agent_id"] == aid
                ),
                D(0),
            )
        else:
            cash = self.db.execute(
                "select coalesce(sum(amount),0) from ledger_entries where experiment_id=%s and agent_id=%s",
                (eid, aid),
            ).fetchone()[0]
        if (
            cash != wallet.cash
            or wallet.cash < 0
            or any(p.quantity < 0 or p.cost < 0 for p in wallet.positions.values())
        ):
            raise RuntimeError("FINANCIAL_INVARIANT_VIOLATION")

    @contextmanager
    def locked(self, experiment_id):
        if self.demo:
            self.db.execute("begin immediate")
            try:
                yield self
                self.db.execute("commit")
            except BaseException:
                self.db.execute("rollback")
                raise
        else:
            with self.db.transaction():
                locked = self.db.execute(
                    "select pg_try_advisory_xact_lock(hashtextextended(%s,0))",
                    (experiment_id,),
                ).fetchone()[0]
                if not locked:
                    raise RuntimeError("Another cycle holds the experiment lock")
                yield self

    def load(self, eid):
        query = "select state from experiments where id=" + ("?" if self.demo else "%s")
        row = self.db.execute(query, (eid,)).fetchone()
        return (json.loads(row[0]) if self.demo else row[0]) if row else None

    def save(self, state, projection):
        eid = state["id"]
        if self.demo:
            self.db.execute(
                "insert into experiments values(?,?) on conflict(id) do update set state=excluded.state",
                (eid, json.dumps(state)),
            )
            return
        # These writes have no intermediate result dependencies. Flush them as
        # one protocol batch inside the caller's existing financial transaction,
        # rather than paying a network round trip for every unchanged market.
        with self.db.pipeline():
            self._save_postgres(state, projection)

    def _save_postgres(self, state, projection):
        eid = state["id"]
        self.db.execute(
            """insert into experiments(id,mode,status,started_at,end_at,state,updated_at)
            values(%s,%s,%s,%s,%s,%s,%s) on conflict(id) do update set status=excluded.status,state=excluded.state,updated_at=excluded.updated_at""",
            (
                eid,
                state["mode"],
                state["status"],
                state["started_at"],
                state["end_at"],
                Jsonb(state),
                state["updated_at"],
            ),
        )
        for a in state["agents"]:
            self.db.execute(
                "insert into strategies values(%s,%s) on conflict(id) do nothing",
                (a["name"], Jsonb({"prompt": a["prompt"]})),
            )
            self.db.execute(
                """insert into agents values(%s,%s,%s,%s,%s,%s) on conflict(experiment_id,id)
                do update set cash=excluded.cash,payload=excluded.payload""",
                (
                    eid,
                    a["id"],
                    a["name"],
                    a["initial_eur"],
                    a["wallet"]["cash"],
                    Jsonb(a),
                ),
            )
            self.db.execute(
                "insert into agent_memories values(%s,%s,%s) on conflict(experiment_id,agent_id) do update set payload=excluded.payload",
                (eid, a["id"], Jsonb(a["memory"])),
            )
        for mid, m in state["markets"].items():
            self.db.execute(
                "insert into markets values(%s,%s) on conflict(id) do update set payload=excluded.payload",
                (mid, Jsonb(m)),
            )
        for a in state["agents"]:
            for p in a["wallet"]["positions"].values():
                self.db.execute(
                    """insert into positions values(%s,%s,%s,%s,%s,%s,%s) on conflict(experiment_id,agent_id,market_id,outcome)
                    do update set quantity=excluded.quantity,cost=excluded.cost,payload=excluded.payload""",
                    (
                        eid,
                        a["id"],
                        p["market_id"],
                        p["outcome"],
                        p["quantity"],
                        p["cost"],
                        Jsonb(p),
                    ),
                )
        self.db.execute(
            "insert into dashboard_states values(%s,%s,%s) on conflict(experiment_id) do update set updated_at=excluded.updated_at,payload=excluded.payload",
            (eid, state["updated_at"], Jsonb(projection)),
        )
        self.db.execute(
            "insert into dashboard_updates values(%s,%s) on conflict(experiment_id) do update set updated_at=excluded.updated_at",
            (eid, state["updated_at"]),
        )

    def record(self, table, **columns):
        if table not in AUDIT_TABLES:
            raise ValueError("Unknown audit table")
        if self.demo:
            identifier = columns.get("id", columns.get("experiment_id"))
            self.db.execute(
                "insert into audit values(?,?,?)",
                (f"{table}:{identifier}", table, json.dumps(columns, default=str)),
            )
            return
        from psycopg import sql

        query = sql.SQL("insert into {} ({}) values ({})").format(
            sql.Identifier(table),
            sql.SQL(",").join(map(sql.Identifier, columns)),
            sql.SQL(",").join(sql.Placeholder() for _ in columns),
        )
        self.db.execute(
            query,
            tuple(
                Jsonb(v) if isinstance(v, (dict, list)) else v for v in columns.values()
            ),
        )

    def learning_history(self, eid, aid):
        """Full authoritative history, never the dashboard's truncated lists."""
        if self.demo:
            rows = [
                json.loads(r[0])
                for r in self.db.execute(
                    "select payload from audit where kind in ('ledger_entries','agent_decisions')"
                )
            ]
            rows = [
                r
                for r in rows
                if r.get("experiment_id") == eid and r.get("agent_id") == aid
            ]
            ledger = [r for r in rows if "kind" in r]
            decisions = {
                r["id"]: r["payload"]
                for r in rows
                if "cycle_id" in r and "kind" not in r
            }
        else:
            ledger = [
                dict(zip(("id", "kind", "created_at", "payload"), r))
                for r in self.db.execute(
                    "select id,kind,created_at,payload from ledger_entries where experiment_id=%s and agent_id=%s",
                    (eid, aid),
                )
            ]
            decisions = dict(
                self.db.execute(
                    "select id,payload from agent_decisions where experiment_id=%s and agent_id=%s",
                    (eid, aid),
                )
            )
            mids = list(
                {
                    r["payload"].get("market_id")
                    or r["payload"].get("position", "").rsplit(":", 1)[0]
                    for r in ledger
                }
            )
            categories = dict(
                self.db.execute(
                    "select id,payload->>'category' from markets where id=any(%s)",
                    (mids,),
                )
            )
            for row in ledger:
                mid = (
                    row["payload"].get("market_id")
                    or row["payload"].get("position", "").rsplit(":", 1)[0]
                )
                if mid in categories and categories[mid]:
                    row["payload"].setdefault("category", categories[mid])
        ledger.sort(
            key=lambda r: (
                str(r["created_at"]),
                0 if r["kind"] == "RESOLUTION" else 1,
                r["id"],
            )
        )
        return ledger, decisions

    def export(self, eid, output):
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        with self.db.transaction() if not self.demo else self.locked(eid):
            if not self.demo:
                self.db.execute(
                    "set transaction isolation level repeatable read read only"
                )
            state = self.load(eid)
            if not state:
                raise ValueError("Unknown experiment")
            (output / "state.json").write_text(
                json.dumps(state, indent=2), encoding="utf-8"
            )
            import csv

            if self.demo:
                with (output / "audit.csv").open(
                    "w", newline="", encoding="utf-8"
                ) as f:
                    writer = csv.writer(f)
                    writer.writerow(["id", "kind", "payload"])
                    writer.writerows(self.db.execute("select * from audit"))
            else:
                for table in AUDIT_TABLES | {
                    "experiments",
                    "strategies",
                    "markets",
                    "dashboard_updates",
                    "analysis_sessions",
                    "llm_meter",
                    "agents",
                    "positions",
                    "agent_memories",
                    "dashboard_states",
                    "llm_attempts",
                    "scheduler_config",
                    "scheduler_dispatches",
                }:
                    from psycopg import sql

                    if (
                        table
                        in (
                            "scheduler_config",
                            "scheduler_dispatches",
                            "analysis_sessions",
                            "llm_meter",
                        )
                        and not self.db.execute(
                            "select to_regclass(%s) is not null", ("public." + table,)
                        ).fetchone()[0]
                    ):
                        continue

                    # Fills carry the experiment through their parent order.
                    query = (
                        sql.SQL("select * from experiments where id=%s")
                        if table == "experiments"
                        else sql.SQL(
                            "select * from strategies where id in (select strategy_id from agents where experiment_id=%s)"
                        )
                        if table == "strategies"
                        else sql.SQL(
                            "select * from markets where id in (select market_id from market_snapshots where experiment_id=%s union select market_id from positions where experiment_id=%s)"
                        )
                        if table == "markets"
                        else sql.SQL(
                            "select f.* from simulated_fills f join simulated_orders o on o.id=f.order_id where o.experiment_id=%s"
                        )
                        if table == "simulated_fills"
                        else sql.SQL("select * from {} where experiment_id=%s").format(
                            sql.Identifier(table)
                        )
                    )
                    cursor = self.db.execute(
                        query, (eid, eid) if table == "markets" else (eid,)
                    )
                    with (output / f"{table}.csv").open(
                        "w", newline="", encoding="utf-8"
                    ) as f:
                        writer = csv.writer(f)
                        writer.writerow([c.name for c in cursor.description])
                        writer.writerows(
                            [
                                json.dumps(v, ensure_ascii=False)
                                if isinstance(v, (dict, list))
                                else v
                                for v in row
                            ]
                            for row in cursor
                        )
