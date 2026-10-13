from datetime import timedelta
from survival.models import utcnow
from survival.runner import make_state
from survival.health import assess


def test_old_successful_schedule_cannot_hide_a_stopped_engine():
    now = utcnow()
    state = make_state("health", "demo", {"usd_per_eur": "1.1"}, now - timedelta(hours=5))
    state["health"] = {"completed_at": state["updated_at"], "market_provider_ok": True}
    state["last_scheduled_cycle"] = state["updated_at"]
    assert assess(state, now)["status"] == "OVERDUE"


def test_current_cycle_distinguishes_technical_failure_from_wait():
    now = utcnow()
    state = make_state("health", "demo", {"usd_per_eur": "1.1"}, now)
    state["health"] = {"completed_at": now.isoformat(), "market_provider_ok": True}
    state["agents"][0]["runtime"] = {"status": "WAIT"}
    assert assess(state, now)["status"] == "HEALTHY"
    state["agents"][0]["runtime"] = {"status": "TECHNICAL_ERROR"}
    assert assess(state, now)["status"] == "DEGRADED"
    state["agents"][0]["last_analysis"] = {"status": "TECHNICAL_ERROR"}
    state["agents"][0]["runtime"] = {"status": "NOT_DUE"}
    assert assess(state, now)["status"] == "DEGRADED"


def test_closure_due_and_finished_are_not_conflated_with_normal_health():
    now = utcnow()
    state = make_state("health", "demo", {"usd_per_eur": "1.1"}, now - timedelta(hours=169))
    assert assess(state, now)["closing_due"]
    state["status"] = "FINISHED"
    assert assess(state, now)["status"] == "FINISHED"
    assert not assess(state, now)["closing_due"]
