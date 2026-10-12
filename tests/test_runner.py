from datetime import timedelta
from decimal import Decimal as D
import sqlite3
import pytest
from survival.models import utcnow
from survival.store import Store
from survival.fixtures import FixtureProvider, FixtureReasoner
from survival.runner import initialize, cycle
from survival.agents import definitions, should_reason


@pytest.fixture
def setup(tmp_path):
    store = Store(demo_path=tmp_path / "test.sqlite")
    now = utcnow()
    initialize(store, "test", "demo", {"usd_per_eur": "1.10"}, now)
    yield store, now
    store.close()


def test_ten_agents_and_pair_isolation(setup):
    store, now = setup
    state = cycle(store, "test", FixtureProvider(now), FixtureReasoner(), "one", now)
    assert len(state["agents"]) == 10
    assert sum(D(a["initial_eur"]) for a in state["agents"]) == 300
    assert state["agents"][0]["wallet"] != state["agents"][5]["wallet"]
    assert len({a["prompt"] for a in state["agents"]}) == 10
    assert all(a["snapshot"] for a in state["agents"])


def test_idempotence(setup):
    store, now = setup
    a = cycle(store, "test", FixtureProvider(now), FixtureReasoner(), "one", now)
    count = store.db.execute("select count(*) from audit").fetchone()[0]
    b = cycle(store, "test", FixtureProvider(now), FixtureReasoner(), "one", now)
    assert a == b
    assert count == store.db.execute("select count(*) from audit").fetchone()[0]


def test_atomic_rollback_and_resume(setup):
    store, now = setup
    original = store.record

    def crash(table, **columns):
        if table == "simulated_fills":
            raise RuntimeError("simulated power loss")
        original(table, **columns)

    store.record = crash
    with pytest.raises(RuntimeError):
        cycle(store, "test", FixtureProvider(now), FixtureReasoner(), "crash", now)
    assert store.load("test")["cycles"] == []
    store.record = original
    # Agent failures are contained, but persistence failures must abort a cycle.
    with pytest.raises(RuntimeError):
        with store.locked("test"):
            state = store.load("test")
            state["status"] = "FINISHED"
            store.save(state, {})
            raise RuntimeError("power loss")
    assert store.load("test")["status"] == "RUNNING"
    state = cycle(
        store, "test", FixtureProvider(now), FixtureReasoner(), "recover", now
    )
    assert state["cycles"] == ["recover"]


def test_no_start_reset(setup):
    store, now = setup
    with pytest.raises(ValueError):
        initialize(store, "test", "demo", {}, now)


def test_finish_no_llm(setup):
    store, now = setup

    class NoLLM:
        def decide(self, *a):
            raise AssertionError("must never be called")

    state = cycle(
        store,
        "test",
        FixtureProvider(now + timedelta(hours=168)),
        NoLLM(),
        "final",
        now + timedelta(hours=168),
    )
    assert state["status"] == "FINISHED"
    assert len(state["report"]["ranking"]) == 10
    assert all(a["memory"].get("calls", 0) == 0 for a in state["agents"])


def test_provider_outage_has_no_fabricated_activity(setup):
    store, now = setup

    class Down:
        errors = []

        def collect(self, *a):
            raise ConnectionError()

    state = cycle(store, "test", Down(), FixtureReasoner(), "outage", now)
    assert state["markets"] == {}
    assert not any(a["orders"] for a in state["agents"])
    assert any(e["kind"] == "ERROR" for e in state["events"])


def test_reasoning_quota_and_unchanged_signal():
    now = utcnow()
    m = FixtureProvider(now).collect()
    a = definitions()[0]
    mem = {"day": now.date().isoformat(), "calls": 12}
    assert not should_reason(mem, list(m.values()), now, a["risk"])
    mem = {"day": now.date().isoformat(), "calls": 1, "last_call": now.isoformat()}
    assert not should_reason(
        mem, list(m.values()), now + timedelta(minutes=10), a["risk"]
    )


def test_sqlite_concurrent_cycle_lock(setup):
    store, now = setup
    path = store.db.execute("pragma database_list").fetchone()[2]
    second = Store(demo_path=path)
    try:
        with store.locked("test"):
            with pytest.raises(sqlite3.OperationalError):
                with second.locked("test"):
                    pass
    finally:
        second.close()
