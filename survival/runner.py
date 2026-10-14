import json
import logging
from datetime import timedelta
from decimal import Decimal as D
from .agents import definitions, SETTINGS
from .models import Wallet, utcnow

log = logging.getLogger(__name__)


def make_state(eid, mode, fx, now):
    agents = []
    for a in definitions():
        initial = D(a["initial_eur"]) * D(fx["usd_per_eur"])
        a.update(
            wallet=Wallet(initial=initial, cash=initial).model_dump(mode="json"),
            memory={},
            stats={
                "peak": str(initial),
                "max_drawdown": "0",
                "trades": 0,
                "wins": 0,
                "closed": 0,
                "categories": {},
            },
            decisions=[],
            orders=[],
        )
        agents.append(a)
    initial_point = {"at": now.isoformat()}
    for a in agents:
        a["snapshot"] = {
            "at": now.isoformat(),
            "nav": a["wallet"]["initial"],
            "nav_eur": a["initial_eur"],
            "cash": a["wallet"]["cash"],
            "invested_cost": "0",
            "realized": "0",
            "unrealized": "0",
            "roi": "0",
            "stranded": [],
            "valuation": "initial cash",
        }
        initial_point[a["id"]] = a["snapshot"]
    return {
        "id": eid,
        "mode": mode,
        "status": "RUNNING",
        "started_at": now.isoformat(),
        "end_at": (now + timedelta(hours=SETTINGS["duration_hours"])).isoformat(),
        "updated_at": now.isoformat(),
        "fx": fx,
        "settings": SETTINGS,
        "agents": agents,
        "markets": {},
        "history": [initial_point],
        "events": [],
        "cycles": [],
        "report": None,
    }


def event(store, state, kind, message, aid=None, details=None):
    from uuid import uuid4

    e = {
        "id": str(uuid4()),
        "at": utcnow().isoformat(),
        "kind": kind,
        "message": message,
        "agent_id": aid,
        "details": details,
    }
    public_event = e.copy()
    if details is not None and len(json.dumps(details, default=str)) > 6000:
        public_event["details"] = {
            "archived_in_system_events": True,
            "tool": details.get("tool") if isinstance(details, dict) else None,
        }
    state["events"].append(public_event)
    state["events"] = state["events"][-500:]
    store.record(
        "system_events",
        id=e["id"],
        experiment_id=state["id"],
        created_at=e["at"],
        payload=e,
    )


def projection(state):
    result = {
        k: v for k, v in state.items() if k not in ("cycles", "completed_request_ids")
    }
    # Full evidence remains in PostgreSQL and exports. A bounded public view
    # prevents each Realtime refresh from downloading all depth and history.
    from .providers import compact_tool

    result["markets"] = {
        mid: compact_tool({"market": m})["market"] | {"history": {}}
        for mid, m in state["markets"].items()
    }
    stride = max(1, __import__("math").ceil(len(state["history"]) / 360))
    points = state["history"][::stride]
    if points and points[-1]["at"] != state["history"][-1]["at"]:
        points.append(state["history"][-1])
    result["chart_sampling"] = {
        "stride": stride,
        "source_points": len(state["history"]),
        "displayed_points": len(points),
        "full_history": "Backend exports and portfolio_snapshots",
    }
    result["history"] = [
        {
            "at": p["at"],
            **{
                a["id"]: {"nav_eur": p[a["id"]]["nav_eur"], "roi": p[a["id"]]["roi"]}
                for a in state["agents"]
            },
        }
        for p in points
    ]
    result["events"] = state["events"][-100:]
    result["agents"] = [
        a | {"decisions": a["decisions"][-10:], "orders": a["orders"][-30:]}
        for a in state["agents"]
    ]
    return result


def initialize(store, eid, mode, fx, now=None):
    now = now or utcnow()
    with store.locked(eid):
        if store.load(eid):
            raise ValueError("Experiment already exists; START is never a reset")
        state = make_state(eid, mode, fx, now)
        store.save(state, projection(state))
        for a in state["agents"]:
            store.record(
                "ledger_entries",
                id=f"{eid}:{a['id']}:initial",
                experiment_id=eid,
                agent_id=a["id"],
                kind="INITIAL",
                amount=a["wallet"]["initial"],
                created_at=now.isoformat(),
                payload={"fx": fx},
            )
        event(store, state, "START", "Explicit START · 168 hour paper competition")
        store.save(state, projection(state))
        return state


from .runtime import cycle as cycle
