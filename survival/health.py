"""Evaluate current liveness, never infer it from an old successful schedule."""

from datetime import datetime
from .models import utcnow


def assess(state, now=None):
    now = now or utcnow()
    health = state.get("health", {})
    stamp = health.get("completed_at") or state["updated_at"]
    age = max(0, (now - datetime.fromisoformat(stamp)).total_seconds())
    if state["status"] == "READY":
        status = "READY"
    elif state["status"] == "FINISHED":
        status = "FINISHED"
    elif (
        state.get("inflight")
        and (now - datetime.fromisoformat(state["updated_at"])).total_seconds()
        < 20 * 60
    ):
        status = "IN_PROGRESS"
    elif age > 20 * 60:
        status = "OVERDUE"
    elif not health.get("market_provider_ok", False):
        status = "PROVIDER_ERROR"
    elif (
        health.get("partial_data")
        or any(
            state.get("phase") != 2 and (a.get("snapshot", {}).get("complete") is False
            or a.get("snapshot", {}).get("stranded")
            and a.get("snapshot", {}).get("complete") is not True)
            for a in state["agents"]
        )
        or health.get("provider_error_count", 0)
        or any(
            a.get("last_analysis", a.get("runtime", {})).get("status")
            in ("TECHNICAL_ERROR", "BUDGET_LIMIT")
            for a in state["agents"]
        )
    ):
        status = "DEGRADED"
    else:
        status = "HEALTHY"
    return {
        "status": status,
        "checked_at": now.isoformat(),
        "cycle_age_seconds": round(age),
        "inflight": state.get("inflight"),
        "closing_due": state["status"] not in ("READY", "FINISHED")
        and now >= datetime.fromisoformat(state["end_at"]),
        "last_cycle_id": health.get("last_cycle_id"),
        "last_github_schedule": state.get("last_scheduled_cycle"),
    }
