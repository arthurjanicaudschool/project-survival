"""Evaluate current liveness, never infer it from an old successful schedule."""
from datetime import datetime
from .models import utcnow


def assess(state, now=None):
    now = now or utcnow()
    health = state.get("health", {})
    stamp = health.get("completed_at") or state["updated_at"]
    age = max(0, (now - datetime.fromisoformat(stamp)).total_seconds())
    if state["status"] == "FINISHED":
        status = "FINISHED"
    elif age > 20 * 60:
        status = "OVERDUE"
    elif not health.get("market_provider_ok", False):
        status = "PROVIDER_ERROR"
    elif any(a.get("last_analysis", a.get("runtime", {})).get("status") == "TECHNICAL_ERROR" for a in state["agents"]):
        status = "DEGRADED"
    else:
        status = "HEALTHY"
    return {"status": status, "checked_at": now.isoformat(), "cycle_age_seconds": round(age),
            "closing_due": state["status"] != "FINISHED" and now >= datetime.fromisoformat(state["end_at"]),
            "last_cycle_id": health.get("last_cycle_id"), "last_github_schedule": state.get("last_scheduled_cycle")}
