import os
from pathlib import Path
from datetime import timedelta
from decimal import Decimal as D
import pytest
import psycopg
from survival.store import Store
from survival.runner import initialize, cycle
from survival.fixtures import FixtureProvider, FixtureReasoner
from survival.models import utcnow


@pytest.mark.integration
def test_live_public_api():
    if os.getenv("RUN_NETWORK_TESTS") != "1":
        pytest.skip("Set RUN_NETWORK_TESTS=1 for public API test")
    from survival.providers import Polymarket

    p = Polymarket()
    try:
        markets = p.collect()
        assert markets and any(m.books for m in markets.values())
        assert all(
            b.evidence and b.minimum > 0
            for m in markets.values()
            for b in m.books.values()
        )
    finally:
        p.close()


@pytest.mark.integration
def test_postgresql_transaction_rls_and_concurrency():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "TEST_DATABASE_URL requires a dedicated disposable PostgreSQL database"
        )
    # Dedicated test database only. No destructive cleanup, unique experiment ID.
    with psycopg.connect(url, autocommit=True) as db:
        db.execute(
            "do $$ begin if not exists(select 1 from pg_roles where rolname='anon') then create role anon; end if; if not exists(select 1 from pg_roles where rolname='authenticated') then create role authenticated; end if; end $$"
        )
        if not db.execute(
            "select 1 from pg_publication where pubname='supabase_realtime'"
        ).fetchone():
            db.execute("create publication supabase_realtime")
        for migration in sorted((Path(__file__).resolve().parent.parent / "supabase/migrations").glob("*.sql")):
            db.execute(migration.read_text(encoding="utf-8"))
    from uuid import uuid4

    eid = f"test-{uuid4()}"
    store = Store(url)
    second = Store(url)
    now = utcnow()
    try:
        initialize(store, eid, "demo", {"usd_per_eur": "1.10"}, now)
        # PostgreSQL is also exercised with isolated demo data; runner mode guard
        # is for live-vs-fixture safety, so use a public-shaped stub for this test.
        state = store.load(eid)
        state["mode"] = "live"
        with store.locked(eid):
            store.save(state, state)

        class PublicShaped:
            errors = []

            def collect(self, *args):
                return FixtureProvider(utcnow()).collect()

        class Reasoner:
            def decide(self, agent, wallet, markets, memory):
                # A research tool can discover a market absent at collection.
                discovered = next(iter(markets.values())).model_copy(deep=True)
                discovered.id = "research-discovered"
                markets[discovered.id] = discovered
                return FixtureReasoner().decide(agent, wallet, markets, memory).model_copy(
                    update={"market_id": discovered.id}
                )

        state = cycle(store, eid, PublicShaped(), Reasoner(), "one", now)
        assert cycle(store, eid, PublicShaped(), Reasoner(), "one", now) == state
        assert store.db.execute(
            "select count(*) from market_snapshots where experiment_id=%s and market_id=%s",
            (eid, "research-discovered"),
        ).fetchone()[0] == 1
        store.db.execute("insert into scheduler_config(experiment_id,repository,enabled) values(%s,'test/repository',true)", (eid,))
        assert not store.db.execute("select survival_watchdog_due(%s,%s)", (eid, now)).fetchone()[0]
        later = now + timedelta(minutes=11)
        assert store.db.execute("select survival_watchdog_due(%s,%s)", (eid, later)).fetchone()[0]
        store.db.execute("insert into scheduler_dispatches(experiment_id,created_at,status) values(%s,%s,'REQUESTED')", (eid, later))
        assert not store.db.execute("select survival_watchdog_due(%s,%s)", (eid, later)).fetchone()[0]
        with store.locked(eid):
            with pytest.raises(RuntimeError):
                with second.locked(eid):
                    pass
        for a in state["agents"]:
            balance = store.db.execute(
                "select sum(amount) from ledger_entries where experiment_id=%s and agent_id=%s",
                (eid, a["id"]),
            ).fetchone()[0]
            assert balance == D(a["wallet"]["cash"])
        with pytest.raises(psycopg.errors.RaiseException):
            store.db.execute(
                "update ledger_entries set amount=0 where experiment_id=%s", (eid,)
            )
        store.db.execute("set role anon")
        assert (
            store.db.execute(
                "select count(*) from dashboard_states where experiment_id=%s", (eid,)
            ).fetchone()[0]
            == 1
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            store.db.execute("select * from ledger_entries")
        store.db.execute("reset role")
        # Full JSON/CSV export can restore into a disposable separate database.
        import tempfile
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict,make_conninfo
        from survival.restore import restore
        database='restore_'+uuid4().hex
        with psycopg.connect(url,autocommit=True) as admin:
            admin.execute(sql.SQL('create database {}').format(sql.Identifier(database)))
        config=conninfo_to_dict(url);config['dbname']=database
        target=Store(make_conninfo(**config))
        try:
            target.db.execute('create publication supabase_realtime')
            for migration in sorted((Path(__file__).resolve().parent.parent/'supabase/migrations').glob('*.sql')):target.db.execute(migration.read_text(encoding='utf-8'))
            with tempfile.TemporaryDirectory() as directory:
                store.export(eid,directory)
                result=restore(target,directory)
                assert result['agents']==10 and result['financial_invariants']=='verified'
                assert target.load(eid)==state
                assert not target.db.execute('select enabled from scheduler_config where experiment_id=%s',(eid,)).fetchone()[0]
        finally:target.close()
    finally:
        store.close()
        second.close()
