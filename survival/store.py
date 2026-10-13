"""Atomic unit of work. PostgreSQL in live mode, SQLite only for demo/tests."""

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
import psycopg
from psycopg.types.json import Jsonb

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
        else:
            self.url = url or os.environ["DATABASE_URL"]
            self.db = psycopg.connect(self.url, autocommit=True, connect_timeout=15)

    def close(self):
        self.db.close()

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

    def export(self, eid, output):
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        with self.locked(eid):
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
                    "agents",
                    "positions",
                    "agent_memories",
                    "dashboard_states",
                    "llm_attempts",
                    "scheduler_config",
                    "scheduler_dispatches",
                }:
                    from psycopg import sql
                    if table in ("scheduler_config", "scheduler_dispatches") and not self.db.execute(
                        "select to_regclass(%s) is not null", ("public." + table,)
                    ).fetchone()[0]:
                        continue

                    # Fills carry the experiment through their parent order.
                    query = (
                        sql.SQL(
                            "select f.* from simulated_fills f join simulated_orders o on o.id=f.order_id where o.experiment_id=%s"
                        )
                        if table == "simulated_fills"
                        else sql.SQL("select * from {} where experiment_id=%s").format(
                            sql.Identifier(table)
                        )
                    )
                    cursor = self.db.execute(query, (eid,))
                    with (output / f"{table}.csv").open(
                        "w", newline="", encoding="utf-8"
                    ) as f:
                        writer = csv.writer(f)
                        writer.writerow([c.name for c in cursor.description])
                        writer.writerows(cursor)
