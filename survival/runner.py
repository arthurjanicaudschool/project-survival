import hashlib
import json
import logging
import os
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
    public_event = e.copy()
    if details is not None and len(json.dumps(details, default=str)) > 6000:
        public_event["details"] = {"archived_in_system_events": True, "tool": details.get("tool") if isinstance(details, dict) else None}
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
        cycle_started = utcnow()
        if "policy_history" not in state:
            state["policy_history"] = [{"at": e["at"], "message": e["message"], "details": e.get("details")} for e in state["events"] if e["kind"] == "POLICY_CHANGE"]
        revision = hashlib.sha256(json.dumps(SETTINGS, sort_keys=True).encode()).hexdigest()[:12]
        if state.get("policy_revision") != revision or state.get("settings", {}).get("policy_version") != SETTINGS["policy_version"]:
            previous = state.get("settings", {})
            configs = {a["id"]: a for a in definitions()}
            for a in state["agents"]:
                a.update({k: configs[a["id"]][k] for k in ("prompt", "risk", "dynamic")})
                a["risk"]["autonomous_discovery"] = True
                a["memory"]["needs_policy_review"] = True
                if not a["risk"].get("prudence_enabled", True):
                    a["memory"].pop("paused_until", None)
                    a["memory"]["pause_triggered"] = False
            state["settings"] = json.loads(json.dumps(SETTINGS))
            state["policy_revision"] = revision
            state["policy_history"].append({"at": cycle_started.isoformat(), "revision": revision,
                                           "previous_policy": previous.get("policy_version", "v1"), "settings": SETTINGS})
            event(store, state, "POLICY_CHANGE", "Autonomous market/web research enabled; A1/A6 unrestricted; other risk limits relaxed. Capital and deadline unchanged.", details={"previous_policy": previous.get("policy_version", "v1"), "new_policy": SETTINGS["policy_version"], "settings": SETTINGS})
        for a in state["agents"]:
            a["risk"]["autonomous_discovery"] = True
        event(store, state, "CYCLE_START", "Cycle started", details={"cycle_id": cycle_id, "at": cycle_started.isoformat()})
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
            if not markets:
                healthy = False
                event(store, state, "ERROR", "No usable public market books; decisions suspended")
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
        snapshotted = set(markets)
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
                and a["risk"].get("prudence_enabled", True)
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
                memory.pop("needs_policy_review", None)
                memory["last_call"] = now.isoformat()
                memory["portfolio_changed"] = False
                memory["prices"] = {
                    f"{m.id}:{o}": str(min(b.asks, key=lambda l: l.price).price)
                    for m in eligible.values()
                    for o, b in m.books.items()
                    if b.asks
                }
                try:
                    try:
                        decision = reasoner.decide(a, wallet, eligible, memory)
                    finally:
                        # Tools can inspect markets outside the original watchlist.
                        markets.update(eligible)
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
                        "decision_status": "WAIT" if decision.action == "WAIT" else "HOLD" if decision.action == "HOLD" else "EXECUTION_REJECTED" if rejection else "EXECUTED",
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
                    a["runtime"] = {"status": payload["decision_status"], "at": utcnow().isoformat(), "reason": rejection or decision.reasoning[:250]}
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
                            "observed_book": markets[decision.market_id].books[decision.outcome].model_dump(mode="json") if decision.market_id in markets and decision.outcome in markets[decision.market_id].books else None,
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
                    diagnostic = {"error_type": type(exc).__name__, "http_status": getattr(exc, "status_code", None),
                                  "code": getattr(exc, "code", None), "parameter": getattr(exc, "param", None)}
                    if hasattr(exc, "errors"):
                        diagnostic["validation"] = [{"field": list(item["loc"]), "type": item["type"]} for item in exc.errors()[:6]]
                    event(
                        store,
                        state,
                        "ERROR",
                        f"Analysis rejected or unavailable: {type(exc).__name__}",
                        a["id"],
                        diagnostic,
                    )
                    a["runtime"] = {"status": "TECHNICAL_ERROR", "at": utcnow().isoformat(), "reason": type(exc).__name__}
                finally:
                    audit = getattr(reasoner, "last_audit", {})
                    if audit:
                        metrics = {k: v for k, v in audit.items() if k != "research"}
                        totals = a["stats"].setdefault("llm_usage", {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0, "cached_prompt_tokens": 0})
                        for key in ("requests", "prompt_tokens", "completion_tokens", "cached_prompt_tokens"):
                            totals[key] += metrics.get(key, 0)
                        totals["model"] = metrics.get("model")
                        totals["metering_started_at"] = totals.get("metering_started_at", utcnow().isoformat())
                        event(store, state, "LLM_USAGE", f"Azure · {metrics.get('requests', 0)} requests · {metrics.get('prompt_tokens', 0)} input / {metrics.get('completion_tokens', 0)} output tokens", a["id"], metrics)
                        for trace in audit.get("research", []):
                            event(store, state, "RESEARCH" if trace["ok"] else "RESEARCH_ERROR", f"{trace['tool']} · {'OK' if trace['ok'] else 'unavailable'}", a["id"], trace)
            else:
                a["runtime"] = {"status": "FINISHED" if ending else "PROVIDER_ERROR" if not healthy else "NOT_DUE", "at": utcnow().isoformat(), "reason": "Deadline reached" if ending else "Market data unavailable" if not healthy else "Waiting for the configured session interval or quota"}
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
        completed = utcnow()
        state["updated_at"] = completed.isoformat()
        state["health"] = {"last_cycle_id": cycle_id, "started_at": cycle_started.isoformat(),
            "completed_at": completed.isoformat(), "duration_seconds": round((completed - cycle_started).total_seconds(), 2),
            "market_count": len(markets), "market_provider_ok": healthy,
            "cycle_count": len(state["cycles"]), "policy_version": SETTINGS["policy_version"],
            "agents": {a["id"]: a.get("runtime", {}) for a in state["agents"]}}
        state["health"]["trigger"] = os.getenv("GITHUB_EVENT_NAME", "local")
        if os.getenv("GITHUB_REPOSITORY") and os.getenv("GITHUB_RUN_ID"):
            state["health"]["logs_url"] = f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        if os.getenv("GITHUB_EVENT_NAME") == "schedule":
            state["last_scheduled_cycle"] = completed.isoformat()
        state["health"]["last_scheduled_cycle"] = state.get("last_scheduled_cycle")
        event(store, state, "CYCLE_COMPLETE", f"Cycle complete · {len(markets)} markets · {len(state['cycles'])} persisted cycles", details=state["health"])
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
                "policy_history": state.get("policy_history", []),
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
        # save upserts newly discovered markets before their snapshot FK is used.
        # Both writes remain inside the same atomic cycle transaction.
        for mid in set(markets) - snapshotted:
            store.record("market_snapshots", id=f"{eid}:{cycle_id}:{mid}", experiment_id=eid,
                         cycle_id=cycle_id, market_id=mid, created_at=utcnow().isoformat(), payload=markets[mid].model_dump(mode="json"))
        return state
