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


def test_policy_upgrade_preserves_capital_deadline_and_reports_health(setup, monkeypatch):
    store, now = setup
    state = store.load("test")
    original_wallet = state["agents"][0]["wallet"].copy()
    end_at = state["end_at"]
    state["settings"]["policy_version"] = "v1"
    store.save(state, {})
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
    state = cycle(store, "test", FixtureProvider(now), FixtureReasoner(), "upgrade", now)
    assert state["end_at"] == end_at
    assert state["agents"][0]["wallet"]["initial"] == original_wallet["initial"]
    assert state["agents"][0]["risk"]["prudence_enabled"] is False
    assert state["health"]["trigger"] == "schedule" and state["health"]["last_scheduled_cycle"]
    assert sum(e["kind"] == "POLICY_CHANGE" for e in state["events"]) == 1
    assert state["health"]["cycle_count"] == 1


def test_valuation_only_cycle_does_not_hide_last_analysis_failure(setup):
    from survival.health import assess
    store, now = setup
    class Broken:
        def decide(self, *args):
            raise ValueError("Provider-shaped failure")
    state = cycle(store, "test", FixtureProvider(now), Broken(), "failed-analysis", now)
    assert all(a["last_analysis"]["status"] == "TECHNICAL_ERROR" for a in state["agents"])
    later = now + timedelta(minutes=10)
    state = cycle(store, "test", FixtureProvider(later), FixtureReasoner(), "valuation", later)
    assert all(a["runtime"]["status"] == "NOT_DUE" for a in state["agents"])
    assert all(a["last_analysis"]["status"] == "TECHNICAL_ERROR" for a in state["agents"])
    assert assess(state, later)["status"] == "DEGRADED"


def test_agents_receive_previous_analysis_time_not_current_reservation(setup):
    store, now = setup
    seen = []
    class InspectMemory:
        def decide(self, agent, wallet, markets, memory):
            seen.append((memory.get("last_call"), memory["session_started_at"]))
            return FixtureReasoner().decide(agent, wallet, markets, memory)
    first = cycle(store, "test", FixtureProvider(now), InspectMemory(), "first-memory", now)
    assert len(seen) == 10 and all(previous is None and current == now.isoformat() for previous, current in seen)
    assert all(a["memory"]["last_call"] == now.isoformat() for a in first["agents"])
    seen.clear()
    later = now + timedelta(hours=6)
    second = cycle(store, "test", FixtureProvider(later), InspectMemory(), "next-memory", later)
    assert len(seen) == 10 and all(previous == now.isoformat() and current == later.isoformat() for previous, current in seen)
    assert all(a["memory"]["last_call"] == later.isoformat() for a in second["agents"])


def test_exploration_fills_are_labelled_and_unestimated_edge_is_not_published(setup):
    from test_participation import affordable, exploration
    store, now=setup
    class Provider:
        errors=[]
        def collect(self,*args):
            return affordable(now)[0]
    class Reasoner:
        def decide(self,agent,wallet,markets,memory):
            if agent["risk"].get("participation_required"):
                return exploration(agent,wallet,markets,wallet.initial*D(".1"))
            return FixtureReasoner().decide(agent,wallet,markets,memory).model_copy(update={"action":"WAIT","outcome":None})
    state=cycle(store,"test",Provider(),Reasoner(),"participation",now)
    for a in state["agents"]:
        if a["id"] in ("A1","A2","A6","A7"):
            assert a["participation"]["status"]=="FULFILLED"
            assert a["orders"][-1]["decision_kind"]=="EXPLORATION"
            assert a["decisions"][-1]["verified_edge"] is None
            assert a["stats"]["exploration_trades"]==1
            assert D(a["wallet"]["cash"]) < D(a["wallet"]["initial"])
        else:
            assert not a["orders"] and a["participation"]["status"]=="DISCRETIONARY"
    assert cycle(store,"test",Provider(),Reasoner(),"participation",now)==state


def test_rejected_exploration_does_not_fulfil_participation(setup):
    from test_participation import affordable, exploration
    store,now=setup
    class Provider:
        errors=[]
        def collect(self,*args):
            return affordable(now)[0]
    class TooSmall:
        def decide(self,agent,wallet,markets,memory):
            if agent["risk"].get("participation_required"):
                return exploration(agent,wallet,markets,".01")
            return FixtureReasoner().decide(agent,wallet,markets,memory).model_copy(update={"action":"WAIT","outcome":None})
    state=cycle(store,"test",Provider(),TooSmall(),"unfilled-participation",now)
    for a in state["agents"]:
        assert a["stats"]["trades"]==0 and a["wallet"]["cash"]==a["wallet"]["initial"]
        if a["participation"]["required"]:
            assert a["participation"]["status"]=="PENDING"
            assert a["orders"][-1]["status"]=="REJECTED"
            assert "participation_fulfilled_at" not in a["memory"]
