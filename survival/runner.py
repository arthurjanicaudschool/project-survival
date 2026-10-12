import hashlib
import json
import logging
import httpx
from openai import OpenAIError
from polymarket.errors import PolymarketError
from datetime import datetime, timedelta
from decimal import Decimal as D
from .agents import definitions, SETTINGS, should_reason
from .models import Wallet, Market, utcnow, ZERO
from .engine import apply, authorize, settle, value

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
    state["events"].append(e)
    state["events"] = state["events"][-500:]
    store.record(
        "system_events",
        id=e["id"],
        experiment_id=state["id"],
        created_at=e["at"],
        payload=e,
    )


def projection(state):
    result = {k: v for k, v in state.items() if k not in ("cycles",)}
    result["history"] = [
        {
            "at": p["at"],
            **{
                a["id"]: {"nav_eur": p[a["id"]]["nav_eur"], "roi": p[a["id"]]["roi"]}
                for a in state["agents"]
            },
        }
        for p in state["history"]
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


def cycle(store, eid, provider, reasoner, cycle_id=None, now=None):
    now = now or utcnow()
    # A rerun in the same scheduled ten-minute slot has the same identity.
    cycle_id = cycle_id or str(int(now.timestamp()) // 600)
    with store.locked(eid):
        state = store.load(eid)
        if not state:
            raise ValueError("No experiment; explicit START required")
        if store.demo != (state["mode"] == "demo"):
            raise ValueError("Storage and experiment modes differ")
        from .fixtures import FixtureProvider, FixtureReasoner

        if state["mode"] == "live" and (
            isinstance(provider, FixtureProvider)
            or isinstance(reasoner, FixtureReasoner)
        ):
            raise ValueError("Synthetic provider forbidden in live mode")
        if state["status"] == "FINISHED" or cycle_id in state["cycles"]:
            return state
        if store.quota_usage()["database_bytes"] >= SETTINGS["max_database_bytes"]:
            raise RuntimeError(
                "Database safety threshold reached; cycles suspended. Export and inspect Supabase usage."
            )
        ending = now >= datetime.fromisoformat(state["end_at"])
        held = {
            p["market_id"]
            for a in state["agents"]
            for p in a["wallet"]["positions"].values()
            if D(p["quantity"]) > 0
        }
        healthy = True
        try:
            markets = provider.collect(held)
        except Exception as exc:
            markets = {}
            healthy = False
            event(
                store,
                state,
                "ERROR",
                f"Market provider unavailable: {type(exc).__name__}. Decisions suspended.",
            )
        for error in provider.errors:
            event(store, state, "ERROR", error)
        # No stale market is reused for execution or valuation.
        state["markets"] = {
            mid: m.model_dump(mode="json") for mid, m in markets.items()
        }
        state["cycles"].append(cycle_id)
        state["updated_at"] = utcnow().isoformat()
        if healthy:
            state["last_market_sync"] = state["updated_at"]
        store.save(state, projection(state))
        store.record(
            "cycles", experiment_id=eid, id=cycle_id, created_at=now.isoformat()
        )
        for mid, m in markets.items():
            store.record(
                "market_snapshots",
                id=f"{eid}:{cycle_id}:{mid}",
                experiment_id=eid,
                cycle_id=cycle_id,
                market_id=mid,
                created_at=now.isoformat(),
                payload=m.model_dump(mode="json"),
            )
        point = {"at": now.isoformat()}
        for a in state["agents"]:
            wallet = Wallet.model_validate(a["wallet"])
            memory = a["memory"]
            for m in markets.values():
                for entry in settle(wallet, m):
                    identifier = (
                        f"{eid}:{cycle_id}:{a['id']}:resolve:{entry['position']}"
                    )
                    store.record(
                        "ledger_entries",
                        id=identifier,
                        experiment_id=eid,
                        agent_id=a["id"],
                        kind="RESOLUTION",
                        amount=entry["amount"],
                        created_at=now.isoformat(),
                        payload=entry,
                    )
                    a["stats"]["closed"] += 1
                    a["stats"]["wins"] += int(D(entry["pnl"]) > 0)
                    category = m.category
                    a["stats"]["categories"][category] = str(
                        D(a["stats"]["categories"].get(category, "0")) + D(entry["pnl"])
                    )
                    memory["portfolio_changed"] = True
                    event(
                        store,
                        state,
                        "RESOLUTION",
                        f"Position resolved · P&L {entry['pnl']} quote",
                        a["id"],
                        entry,
                    )
            nav, _, unpriced = value(
                wallet,
                markets,
                utcnow() if state["mode"] == "live" else now,
                SETTINGS["max_age_seconds"],
            )
            peak = max(D(a["stats"]["peak"]), nav)
            drawdown = 1 - nav / peak
            if not unpriced:
                a["stats"]["peak"] = str(peak)
                a["stats"]["max_drawdown"] = str(
                    max(D(a["stats"]["max_drawdown"]), drawdown)
                )
            if (
                not unpriced
                and drawdown >= D(a["risk"]["pause_drawdown"])
                and not memory.get("pause_triggered")
            ):
                memory["paused_until"] = (
                    now + timedelta(hours=a["risk"]["cooldown_hours"])
                ).isoformat()
                memory["pause_triggered"] = True
                event(
                    store,
                    state,
                    "RISK",
                    "Drawdown limit reached; new exposure temporarily suspended",
                    a["id"],
                )
            elif drawdown < D(a["risk"]["pause_drawdown"]):
                memory["pause_triggered"] = False
            eligible = {
                mid: m
                for mid, m in markets.items()
                if m.active
                and any(
                    b.asks
                    and (now - b.observed_at).total_seconds()
                    <= SETTINGS["max_age_seconds"]
                    for b in m.books.values()
                )
            }
            if (
                not ending
                and healthy
                and should_reason(memory, list(eligible.values()), now, a["risk"])
                and store.reserve_llm(
                    eid, a["id"], cycle_id, now, a["risk"]["calls_per_day"]
                )
            ):
                # Count attempted requests too, including validation/provider failure.
                memory["calls"] = memory.get("calls", 0) + 1
                memory["last_call"] = now.isoformat()
                memory["portfolio_changed"] = False
                memory["prices"] = {
                    f"{m.id}:{o}": str(min(b.asks, key=lambda l: l.price).price)
                    for m in eligible.values()
                    for o, b in m.books.items()
                    if b.asks
                }
                try:
                    decision = reasoner.decide(a, wallet, eligible, memory)
                    execution_time = utcnow() if state["mode"] == "live" else now
                    # An LLM that crosses the deadline cannot cause a trade.
                    if execution_time >= datetime.fromisoformat(state["end_at"]):
                        raise ValueError(
                            "Deadline crossed during analysis; decision not executed"
                        )
                    if hasattr(provider, "refresh") and decision.action in (
                        "BUY",
                        "SELL",
                    ):
                        provider.refresh(markets[decision.market_id], decision.outcome)
                        execution_time = utcnow()
                    if execution_time >= datetime.fromisoformat(state["end_at"]):
                        raise ValueError("Deadline crossed during book refresh")
                    execution, rejection, edge = authorize(
                        a, wallet, decision, markets, execution_time, memory
                    )
                    did = f"{eid}:{cycle_id}:{a['id']}"
                    payload = decision.model_dump(mode="json") | {
                        "verified_edge": str(edge),
                        "at": now.isoformat(),
                        "rejection": rejection,
                    }
                    store.record(
                        "agent_decisions",
                        id=did,
                        experiment_id=eid,
                        agent_id=a["id"],
                        cycle_id=cycle_id,
                        created_at=now.isoformat(),
                        payload=payload,
                    )
                    a["decisions"] = (a["decisions"] + [payload])[-30:]
                    memory["summary"] = decision.reasoning[:1500]
                    memory["exit_plan"] = decision.exit_plan
                    event(
                        store, state, "ANALYSIS", decision.reasoning, a["id"], payload
                    )
                    if decision.action in ("BUY", "SELL"):
                        order = {
                            "id": did,
                            "at": now.isoformat(),
                            "market_id": decision.market_id,
                            "outcome": decision.outcome,
                            "action": decision.action,
                            "status": execution.status if execution else "REJECTED",
                            "reason": rejection,
                            "execution": execution.model_dump(mode="json")
                            if execution
                            else None,
                        }
                        store.record(
                            "simulated_orders",
                            id=did,
                            experiment_id=eid,
                            agent_id=a["id"],
                            decision_id=did,
                            status=order["status"],
                            created_at=now.isoformat(),
                            payload=order,
                        )
                        a["orders"] = (a["orders"] + [order])[-100:]
                        if execution and execution.fills:
                            pnl = apply(
                                wallet,
                                decision.market_id,
                                decision.outcome,
                                decision.action,
                                execution,
                            )
                            for i, f in enumerate(execution.fills):
                                store.record(
                                    "simulated_fills",
                                    id=f"{did}:{i}",
                                    order_id=did,
                                    quantity=str(f.quantity),
                                    price=str(f.price),
                                    fee=str(f.fee),
                                    payload=f.model_dump(mode="json"),
                                )
                            delta = (
                                -(execution.gross + execution.fees)
                                if decision.action == "BUY"
                                else execution.gross - execution.fees
                            )
                            store.record(
                                "ledger_entries",
                                id=did,
                                experiment_id=eid,
                                agent_id=a["id"],
                                kind=decision.action,
                                amount=str(delta),
                                created_at=now.isoformat(),
                                payload=order | {"realized_pnl": str(pnl)},
                            )
                            a["stats"]["trades"] += 1
                            if decision.action == "SELL":
                                a["stats"]["closed"] += 1
                                a["stats"]["wins"] += int(pnl > 0)
                                category = markets[decision.market_id].category
                                a["stats"]["categories"][category] = str(
                                    D(a["stats"]["categories"].get(category, "0")) + pnl
                                )
                            memory["portfolio_changed"] = True
                            event(
                                store,
                                state,
                                decision.action,
                                f"Paper {decision.action} · {execution.quantity} {decision.outcome} · {execution.status}",
                                a["id"],
                                order,
                            )
                        else:
                            event(store, state, "REJECTION", rejection, a["id"], order)
                except (
                    ValueError,
                    KeyError,
                    httpx.HTTPError,
                    OpenAIError,
                    PolymarketError,
                ) as exc:
                    log.warning("Agent %s failed: %s", a["id"], type(exc).__name__)
                    event(
                        store,
                        state,
                        "ERROR",
                        f"Analysis rejected or unavailable: {type(exc).__name__}",
                        a["id"],
                    )
            valuation_time = utcnow() if state["mode"] == "live" else now
            nav, invested, stranded = value(
                wallet, markets, valuation_time, SETTINGS["max_age_seconds"]
            )
            roi = nav / wallet.initial - 1
            peak = max(D(a["stats"]["peak"]), nav)
            if not stranded:
                a["stats"]["peak"] = str(peak)
                a["stats"]["max_drawdown"] = str(
                    max(D(a["stats"]["max_drawdown"]), 1 - nav / peak)
                )
            snapshot = {
                "at": valuation_time.isoformat(),
                "nav": str(nav),
                "cash": str(wallet.cash),
                "invested_cost": str(invested),
                "realized": str(wallet.realized),
                "unrealized": str(nav - wallet.cash - invested),
                "roi": str(roi),
                "nav_eur": str(nav / D(state["fx"]["usd_per_eur"])),
                "stranded": stranded,
                "valuation": "conservative liquidatable lower bound"
                if stranded
                else "observed bid depth after fees",
            }
            a["wallet"] = wallet.model_dump(mode="json")
            a["snapshot"] = snapshot
            point[a["id"]] = snapshot
            store.record(
                "portfolio_snapshots",
                id=f"{eid}:{cycle_id}:{a['id']}",
                experiment_id=eid,
                agent_id=a["id"],
                created_at=valuation_time.isoformat(),
                payload=snapshot,
            )
        # Dashboard keeps hourly samples plus the latest cycle. Full ten-minute
        # financial snapshots remain append-only in portfolio_snapshots.
        hour = now.isoformat()[:13]
        if len(state["history"]) > 1 and state["history"][-1]["at"][:13] == hour:
            state["history"][-1] = point
        else:
            state["history"].append(point)
        # Preserve full seven-day timeline; no unbounded updates after FINISHED.
        state["markets"] = {
            mid: m.model_dump(mode="json") for mid, m in markets.items()
        }
        if ending:
            state["status"] = "FINISHED"
            ranking = sorted(
                state["agents"],
                key=lambda a: (-D(a["snapshot"]["roi"]), int(a["id"][1:])),
            )
            absolute = max(
                state["agents"],
                key=lambda a: D(a["snapshot"]["nav"]) - D(a["wallet"]["initial"]),
            )
            strategies = {}
            for a in ranking:
                strategies.setdefault(a["name"], []).append(
                    {
                        "agent_id": a["id"],
                        "roi": a["snapshot"]["roi"],
                        "drawdown": a["stats"]["max_drawdown"],
                    }
                )
            state["report"] = {
                "generated_at": utcnow().isoformat(),
                "deadline": state["end_at"],
                "valuation_time": now.isoformat(),
                "close_delay_seconds": max(
                    0, (now - datetime.fromisoformat(state["end_at"])).total_seconds()
                ),
                "ranking": [
                    {
                        "agent_id": a["id"],
                        "roi": a["snapshot"]["roi"],
                        "profit_eur": str(
                            D(a["snapshot"]["nav_eur"]) - D(a["initial_eur"])
                        ),
                        "survives": D(a["snapshot"]["roi"])
                        > D(SETTINGS["survival_roi"]),
                        "stranded": a["snapshot"]["stranded"],
                        "return_over_max_drawdown": str(
                            D(a["snapshot"]["roi"]) / D(a["stats"]["max_drawdown"])
                        )
                        if D(a["stats"]["max_drawdown"]) > 0
                        else None,
                    }
                    for a in ranking
                ],
                "roi_winner": ranking[0]["id"],
                "absolute_winner": absolute["id"],
                "strategies": strategies,
                "strategy_summary": {
                    name: {
                        "mean_roi": str(
                            sum((D(row["roi"]) for row in pair), ZERO) / len(pair)
                        ),
                        "mean_max_drawdown": str(
                            sum((D(row["drawdown"]) for row in pair), ZERO) / len(pair)
                        ),
                        "survivors": sum(
                            D(row["roi"]) > D(SETTINGS["survival_roi"]) for row in pair
                        ),
                        "comparison": f"{pair[0]['agent_id']} led the pair by net ROI; capital effects and a seven-day sample do not establish a persistent edge.",
                    }
                    for name, pair in strategies.items()
                },
                "incomplete_valuation": any(a["snapshot"]["stranded"] for a in ranking),
                "limitation": "Final books observed on closing cycle, not a guaranteed exact-deadline quote. Stranded shares valued at zero as a lower bound. No evidence of future profitability.",
            }
            store.record(
                "final_reports",
                experiment_id=eid,
                created_at=now.isoformat(),
                payload=state["report"],
            )
            event(store, state, "FINISH", "Competition complete · final report saved")
        store.save(state, projection(state))
        return state
