"""Resumable agent tasks and short, idempotent financial transactions."""

import copy
import hashlib
import json
import os
from datetime import datetime, timedelta
from decimal import Decimal as D
from .models import Wallet, Decision, DecisionPlan, utcnow, ZERO
from .agents import SETTINGS, definitions, should_reason
from .engine import apply, authorize, settle, valuation
from .learning import build_feedback, accept_reviews
from .analytics import classify, risk_exposure, performance, observed_drawdown


def clock(state, now):
    return utcnow() if state["mode"] == "live" else now


def fingerprint(wallet):
    return hashlib.sha256(wallet.model_dump_json().encode()).hexdigest()


def archived_market(m, held=False):
    data = m.model_dump(mode="json")
    data["history"] = {}
    if not held:
        for b in data["books"].values():
            b["bids"] = b["bids"][:5]
            b["asks"] = b["asks"][:5]
    return data


def archive_held_observations(store, state, agent, wallet, markets, cid, at):
    for mid in {p.market_id for p in wallet.positions.values() if p.quantity > 0}:
        m = markets.get(mid)
        if not m:
            continue
        data = archived_market(m, True)
        digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[
            :16
        ]
        sid = f"{state['id']}:{cid}:held:{agent['id']}:{mid}:{digest}"
        if not store.audit_exists("market_snapshots", sid):
            store.record(
                "market_snapshots",
                id=sid,
                experiment_id=state["id"],
                cycle_id=cid,
                market_id=mid,
                created_at=at.isoformat(),
                payload=data,
            )


def snapshot(a, markets, at, fx, max_age=None, history=()):
    wallet = Wallet.model_validate(a["wallet"])
    v = valuation(wallet, markets, at, max_age or SETTINGS["max_age_seconds"])
    nav = D(v["nav"]) if v["complete"] else None
    observed_drawdown(a, history, nav, fx)
    v.update(
        at=at.isoformat(),
        cash=str(wallet.cash),
        realized=str(wallet.realized),
        nav_eur=str(nav / fx) if nav is not None else None,
        nav_lower_bound_eur=str(D(v["nav_lower_bound"]) / fx),
        nav_upper_bound_eur=str(D(v["nav_upper_bound"]) / fx),
        unrealized=str(nav - wallet.cash - D(v["invested_cost"]))
        if nav is not None
        else None,
    )
    a["snapshot"] = v
    a["stats"]["exposure"] = risk_exposure(wallet, markets)
    return v


def feedback(store, state, a, markets, at):
    ledger, decisions = store.learning_history(state["id"], a["id"])
    old = a["memory"].get("learning", {})
    f = build_feedback(
        ledger,
        decisions,
        {k: v.model_dump(mode="json") for k, v in markets.items()},
        old,
    )
    f["updated_at"] = at.isoformat()
    a["memory"]["learning"] = f
    # Forecasts are evaluated independently of whether a position was retained.
    scores = []
    resolved = a["memory"].setdefault("resolved_forecasts", {})
    resolved.update(
        {
            m.id: str(m.payouts["YES"])
            for m in markets.values()
            if m.resolved and "YES" in m.payouts
        }
    )
    for did, d in decisions.items():
        mid = d.get("market_id")
        if mid in resolved and d.get("probability_basis", "ESTIMATED") == "ESTIMATED":
            scores.append(
                (mid, (D(d["estimated_probability"]) - D(resolved[mid])) ** 2)
            )
    f["all_decision_calibration"] = {
        "scored_decisions": len(scores),
        "unique_markets": len({s[0] for s in scores}),
        "brier_score": str(sum((s[1] for s in scores), ZERO) / len(scores))
        if scores
        else None,
        "limitation": "Only resolutions observed by the system. Repeated forecasts on one market are correlated.",
    }
    if not old or old.get("closed_events") != f["closed_events"]:
        from .runner import event

        event(
            store,
            state,
            "LEARNING",
            f"Outcome feedback · {f['closed_events']} exits · {len(scores)} resolved forecasts",
            a["id"],
            f,
        )


def record_trade(store, state, a, wallet, d, markets, cid, suffix, at):
    from .runner import event

    did = f"{state['id']}:{cid}:{a['id']}:{suffix}"
    if d.action in ("BUY", "SELL") and d.market_id in markets:
        store.record(
            "market_snapshots",
            id=did + ":quote",
            experiment_id=state["id"],
            cycle_id=cid,
            market_id=d.market_id,
            created_at=at.isoformat(),
            payload=archived_market(markets[d.market_id], True),
        )
    execution, rejection, edge = authorize(a, wallet, d, markets, at, a["memory"])
    lessons = {
        r.get("id", r.get("decision_id"))
        for r in a["memory"].get("learning", {}).get("reviews", [])
    }
    d.applied_lesson_ids = [i for i in d.applied_lesson_ids if i in lessons]
    data = d.model_dump(mode="json") | {
        "id": did,
        "at": at.isoformat(),
        "verified_edge": str(edge)
        if d.probability_basis != "UNESTIMATED"
        or d.thesis_type == "PRICE_MOVE"
        and d.action == "BUY"
        else None,
        "edge_basis": "target-price scenario, not expected return"
        if d.thesis_type == "PRICE_MOVE" and d.action == "BUY"
        else "net sale vs estimated payout"
        if d.action == "SELL"
        else "estimated payout vs all-in entry",
        "rejection": rejection,
        "decision_status": "EXECUTION_REJECTED"
        if rejection
        else "EXECUTED"
        if d.action in ("BUY", "SELL")
        else d.action,
    }
    store.record(
        "agent_decisions",
        id=did,
        experiment_id=state["id"],
        agent_id=a["id"],
        cycle_id=cid,
        created_at=at.isoformat(),
        payload=data,
    )
    a["decisions"] = (a["decisions"] + [data])[-40:]
    accepted, rejected = accept_reviews(
        a["memory"]["learning"], d.learning_review, at.isoformat(), did
    )
    if accepted or rejected:
        event(
            store,
            state,
            "LEARNING_REVIEW",
            f"{len(accepted)} grounded hypotheses; {rejected} unsupported references excluded",
            a["id"],
            {"accepted": accepted, "rejected_references": rejected},
        )
    if d.action == "HOLD" and d.exit_rules and d.outcome:
        p = wallet.positions.get(f"{d.market_id}:{d.outcome}")
        if p:
            p.exit_rules = d.exit_rules
            p.exit_plan = d.exit_plan
    if d.action in ("BUY", "SELL"):
        book = (
            markets.get(d.market_id).books.get(d.outcome)
            if d.market_id in markets
            else None
        )
        order = {
            "id": did,
            "at": at.isoformat(),
            "market_id": d.market_id,
            "outcome": d.outcome,
            "action": d.action,
            "decision_kind": d.decision_kind,
            "probability_basis": d.probability_basis,
            "thesis_type": d.thesis_type,
            "status": execution.status if execution else "REJECTED",
            "reason": rejection,
            "execution": execution.model_dump(mode="json") if execution else None,
            "observed_book": book.model_dump(mode="json") if book else None,
            "simulation_method": "FAK against observed depth; independent counterfactual portfolio, no real matching confirmation",
        }
        store.record(
            "simulated_orders",
            id=did,
            experiment_id=state["id"],
            agent_id=a["id"],
            decision_id=did,
            status=order["status"],
            created_at=at.isoformat(),
            payload=order,
        )
        a["orders"] = (a["orders"] + [order])[-100:]
        if execution and execution.fills:
            pnl = apply(wallet, d.market_id, d.outcome, d.action, execution)
            p = wallet.positions[f"{d.market_id}:{d.outcome}"]
            if d.action == "BUY":
                p.exit_rules = d.exit_rules
                p.exit_plan = d.exit_plan
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
                if d.action == "BUY"
                else execution.gross - execution.fees
            )
            store.record(
                "ledger_entries",
                id=did,
                experiment_id=state["id"],
                agent_id=a["id"],
                kind=d.action,
                amount=str(delta),
                created_at=at.isoformat(),
                payload=order
                | {
                    "realized_pnl": str(pnl),
                    "category": markets[d.market_id].category,
                    "position_quantity_after": str(p.quantity),
                    "applied_lesson_ids": d.applied_lesson_ids,
                },
            )
            a["stats"]["trades"] += 1
            if d.decision_kind == "EXPLORATION":
                a["stats"]["exploration_trades"] = (
                    a["stats"].get("exploration_trades", 0) + 1
                )
            if d.action == "BUY":
                a["memory"].setdefault("participation_fulfilled_at", at.isoformat())
            if d.action == "SELL":
                a["stats"]["closed"] += 1
                a["stats"]["wins"] += int(pnl > 0)
                c = markets[d.market_id].category
                a["stats"]["categories"][c] = str(
                    D(a["stats"]["categories"].get(c, "0")) + pnl
                )
            a["memory"]["portfolio_changed"] = True
            # One portfolio cannot reuse the same observed depth for subsequent
            # actions. Other agents remain independent counterfactual portfolios.
            if book:
                levels = book.asks if d.action == "BUY" else book.bids
                consumed = {}
                for f in execution.fills:
                    consumed[f.price] = consumed.get(f.price, ZERO) + f.quantity
                remaining = []
                for level in levels:
                    used = min(level.size, consumed.get(level.price, ZERO))
                    consumed[level.price] = consumed.get(level.price, ZERO) - used
                    if level.size > used:
                        remaining.append(
                            level.model_copy(update={"size": level.size - used})
                        )
                if d.action == "BUY":
                    book.asks = remaining
                else:
                    book.bids = remaining
            event(
                store,
                state,
                d.action,
                f"Paper {d.action} · {d.decision_kind} · {execution.quantity} {d.outcome}",
                a["id"],
                order,
            )
        else:
            event(store, state, "REJECTION", rejection, a["id"], order)
    else:
        event(store, state, "ANALYSIS", d.reasoning, a["id"], data)
    a["runtime"] = {
        "status": data["decision_status"],
        "at": at.isoformat(),
        "reason": rejection or d.reasoning[:250],
    }
    a["memory"]["summary"] = d.reasoning[:1500]
    a["memory"]["exit_plan"] = d.exit_plan
    return data


def settlements(store, state, a, wallet, markets, at, cutoff=None):
    from .runner import event

    for m in markets.values():
        if cutoff and (not m.resolved_at or m.resolved_at > cutoff):
            continue
        for entry in settle(wallet, m):
            did = f"{state['id']}:{a['id']}:resolution:{entry['position']}"
            store.record(
                "ledger_entries",
                id=did,
                experiment_id=state["id"],
                agent_id=a["id"],
                kind="RESOLUTION",
                amount=entry["amount"],
                created_at=at.isoformat(),
                payload=entry,
            )
            a["stats"]["closed"] += 1
            a["stats"]["wins"] += int(D(entry["pnl"]) > 0)
            a["stats"]["categories"][m.category] = str(
                D(a["stats"]["categories"].get(m.category, "0")) + D(entry["pnl"])
            )
            a["memory"]["portfolio_changed"] = True
            event(
                store,
                state,
                "RESOLUTION",
                f"Observed resolution · P&L {entry['pnl']}",
                a["id"],
                entry,
            )


def automatic_exits(a, wallet, markets, at):
    for key, p in wallet.positions.items():
        m = markets.get(p.market_id)
        b = m.books.get(p.outcome) if m else None
        r = p.exit_rules
        if (
            p.quantity <= 0
            or not r
            or not b
            or not b.bids
            or (at - b.observed_at).total_seconds() > SETTINGS["max_age_seconds"]
        ):
            continue
        bid = max(l.price for l in b.bids)
        trigger = (
            "STOP"
            if r.stop_bid is not None and bid <= r.stop_bid
            else "TAKE_PROFIT"
            if r.take_profit_bid is not None and bid >= r.take_profit_bid
            else "TIME_EXIT"
            if r.exit_at and at >= r.exit_at
            else None
        )
        if trigger:
            yield (
                key,
                Decision(
                    agent_id=a["id"],
                    market_id=m.id,
                    outcome=p.outcome,
                    action="SELL",
                    estimated_probability=D(".5"),
                    confidence=0,
                    reasoning=f"Agent-selected structured rule triggered: {trigger}. Observed bid {bid}; execution not guaranteed.",
                    sources=[],
                    proposed_stake=0,
                    expected_edge=0,
                    exit_plan=p.exit_plan,
                    risk_factors=["Price and liquidity can change"],
                    probability_basis="UNESTIMATED",
                    close_position=True,
                    min_sell_price=max(
                        b.tick, bid - D(a["risk"].get("max_slippage", "0.03"))
                    ),
                ),
            )


def refresh_positions(provider, wallet, markets):
    if not hasattr(provider, "refresh"):
        return
    for p in wallet.positions.values():
        m = markets.get(p.market_id)
        if p.quantity > 0 and m and m.active and p.outcome in m.books:
            try:
                provider.refresh(m, p.outcome)
            except Exception as exc:
                m.books.pop(p.outcome, None)
                provider.errors.append(
                    f"Position refresh {p.market_id}/{p.outcome}: {type(exc).__name__}"
                )


def cycle(store, eid, provider, reasoner, cycle_id=None, now=None):
    from .runner import projection, event
    from .fixtures import FixtureProvider, FixtureReasoner
    from .participation import status as participation_status

    now = now or utcnow()
    requested_id = cycle_id or str(int(now.timestamp()) // 600)
    with store.lease(eid):
        state = store.load(eid)
        if not state:
            raise ValueError("No experiment; explicit START required")
        if store.demo != (state["mode"] == "demo"):
            raise ValueError("Storage and experiment modes differ")
        if state["mode"] == "live" and (
            isinstance(provider, FixtureProvider)
            or isinstance(reasoner, FixtureReasoner)
        ):
            raise ValueError("Synthetic provider forbidden in live mode")
        if (
            state["status"] == "FINISHED"
            or requested_id in state["cycles"]
            or requested_id in state.get("completed_request_ids", [])
        ):
            return state
        cid = state.get("inflight", {}).get("id", requested_id)
        if store.quota_usage()["database_bytes"] >= SETTINGS["max_database_bytes"]:
            raise RuntimeError("Database safety threshold reached")
        started = utcnow()
        ending = now >= datetime.fromisoformat(state["end_at"])
        held = {
            p["market_id"]
            for a in state["agents"]
            for p in a["wallet"]["positions"].values()
            if D(p["quantity"]) > 0
        }
        # Retain recently researched markets for forecast follow-up, independent of holdings.
        tracked = {
            d["market_id"]
            for a in state["agents"]
            for d in a["decisions"][-3:]
            if d.get("market_id")
        }
        forecasts = sorted(
            {
                d["market_id"]
                for a in state["agents"]
                for d in a["decisions"]
                if d.get("market_id")
                and d.get("probability_basis", "ESTIMATED") == "ESTIMATED"
                and d["market_id"] not in a["memory"].get("resolved_forecasts", {})
            }
        )
        if forecasts:
            start = len(state["cycles"]) * SETTINGS["forecast_followup_per_cycle"]
            tracked.update(
                forecasts[(start + i) % len(forecasts)]
                for i in range(
                    min(len(forecasts), SETTINGS["forecast_followup_per_cycle"])
                )
            )
        try:
            markets = provider.collect(held | tracked)
            provider_ok = bool(markets)
        except Exception as exc:
            markets = {}
            provider_ok = False
            provider.errors = [f"Market provider: {type(exc).__name__}"]
        for m in markets.values():
            if m.category_source == "unknown":
                m.category, m.category_source = classify(m.question, m.category)
        seed = copy.deepcopy(markets)
        with store.locked(eid):
            if not state.get("inflight"):
                state["inflight"] = {
                    "id": cid,
                    "started_at": started.isoformat(),
                    "completed_agents": [],
                    "request_ids": [requested_id],
                }
                store.record(
                    "cycles", experiment_id=eid, id=cid, created_at=now.isoformat()
                )
                event(
                    store,
                    state,
                    "CYCLE_START",
                    "Resumable cycle started",
                    details={"cycle_id": cid},
                )
            if requested_id not in state["inflight"].setdefault("request_ids", []):
                state["inflight"]["request_ids"].append(requested_id)
            revision = hashlib.sha256(
                json.dumps(SETTINGS, sort_keys=True).encode()
            ).hexdigest()[:12]
            if state.get("policy_revision") != revision:
                old = state.get("settings", {}).get("policy_version")
                for a, config in zip(state["agents"], definitions()):
                    a.update({k: config[k] for k in ("prompt", "risk", "dynamic")})
                    a["risk"]["autonomous_discovery"] = True
                    a["memory"]["needs_policy_review"] = True
                state.setdefault("policy_history", []).append(
                    {
                        "at": now.isoformat(),
                        "previous_policy": old,
                        "revision": revision,
                        "settings": SETTINGS,
                        "baseline_nav": {
                            a["id"]: a["snapshot"].get("nav")
                            if not a["snapshot"].get("stranded")
                            else None
                            for a in state["agents"]
                        },
                    }
                )
                state["settings"] = copy.deepcopy(SETTINGS)
                state["policy_revision"] = revision
                event(
                    store,
                    state,
                    "POLICY_CHANGE",
                    f"Policy {SETTINGS['policy_version']} · preserved capital, deadline and historical phases",
                    details=state["policy_history"][-1],
                )
            state["markets"] = {
                k: v.model_dump(mode="json") for k, v in markets.items()
            }
            state["updated_at"] = utcnow().isoformat()
            store.save(state, projection(state))
            for mid, m in markets.items():
                # Capture observations immediately, before long reasoning or the deadline.
                sid = f"{eid}:{cid}:initial:{mid}"
                if not store.audit_exists("market_snapshots", sid):
                    store.record(
                        "market_snapshots",
                        id=sid,
                        experiment_id=eid,
                        cycle_id=cid,
                        market_id=mid,
                        created_at=clock(state, now).isoformat(),
                        payload=archived_market(m, mid in held),
                    )
            for error in provider.errors:
                event(store, state, "ERROR", error)
        agent_order = sorted(
            state["agents"], key=lambda a: a["memory"].get("last_call", "")
        )
        for a in agent_order:
            if (
                a["initial_eur"] == "10"
                and a["risk"].get("prudence_enabled", True)
                and not a["dynamic"]
            ):
                a["risk"]["small_account_minimum_fraction"] = SETTINGS[
                    "small_account_minimum_fraction"
                ]
            if a["id"] in state["inflight"]["completed_agents"]:
                continue
            at = clock(state, now)
            ending = at >= datetime.fromisoformat(state["end_at"])
            wallet = Wallet.model_validate(a["wallet"])
            memory = a["memory"]
            local = copy.deepcopy(seed)
            refresh_positions(provider, wallet, local)
            markets.update(local)
            prepared = a["id"] in state["inflight"].get("prepared_agents", [])
            exits = (
                list(automatic_exits(a, wallet, local, at))
                if not ending and not prepared
                else []
            )
            from .providers import Polymarket

            for key, d in exits:
                if isinstance(provider, Polymarket):
                    try:
                        provider.refresh(
                            local[d.market_id], d.outcome, for_execution=True
                        )
                    except Exception as exc:
                        local[d.market_id].books.pop(d.outcome, None)
                        provider.errors.append(
                            f"Exit refresh {d.market_id}: {type(exc).__name__}"
                        )
            at = clock(state, now)
            ending = at >= datetime.fromisoformat(state["end_at"])
            if ending:
                exits = []
            with store.locked(eid):
                if hasattr(provider, "refresh"):
                    archive_held_observations(store, state, a, wallet, local, cid, at)
                if a["id"] not in state["inflight"].get("prepared_agents", []):
                    settlements(
                        store,
                        state,
                        a,
                        wallet,
                        local,
                        at,
                        datetime.fromisoformat(state["end_at"]) if ending else None,
                    )
                a["wallet"] = wallet.model_dump(mode="json")
                feedback(store, state, a, local, at)
                if a["risk"].get("participation_required"):
                    memory.setdefault("participation_started_at", at.isoformat())
                a["participation"] = participation_status(a, at, state["end_at"])
                v = snapshot(
                    a,
                    local,
                    at,
                    D(state["fx"]["usd_per_eur"]),
                    history=state["history"],
                )
                current_drawdown = (
                    1 - D(v["nav"]) / D(a["stats"]["peak"]) if v["complete"] else None
                )
                if current_drawdown is not None and current_drawdown < D(
                    a["risk"]["pause_drawdown"]
                ):
                    memory.pop("pause_triggered", None)
                if (
                    current_drawdown is not None
                    and a["risk"].get("prudence_enabled", True)
                    and current_drawdown >= D(a["risk"]["pause_drawdown"])
                    and not memory.get("pause_triggered")
                ):
                    memory["paused_until"] = (
                        at + timedelta(hours=a["risk"]["cooldown_hours"])
                    ).isoformat()
                    memory["pause_triggered"] = True
                if not ending and a["id"] not in state["inflight"].get(
                    "prepared_agents", []
                ):
                    for key, d in exits:
                        record_trade(
                            store,
                            state,
                            a,
                            wallet,
                            d,
                            local,
                            cid,
                            "exit:" + key,
                            clock(state, now),
                        )
                if a["id"] not in state["inflight"].setdefault("prepared_agents", []):
                    state["inflight"]["prepared_agents"].append(a["id"])
                a["wallet"] = wallet.model_dump(mode="json")
                state["inflight"]["current_agent"] = a["id"]
                state["updated_at"] = utcnow().isoformat()
                store.save(state, projection(state))
            task_id = f"{eid}:{cid}:{a['id']}"
            task = store.task_get(task_id)
            eligible = {k: v for k, v in local.items() if v.active}
            due = (
                not ending
                and provider_ok
                and should_reason(memory, list(eligible.values()), at, a["risk"])
            )
            deferred = (
                not ending
                and (utcnow() - started).total_seconds()
                >= SETTINGS["cycle_analysis_budget_seconds"]
            )
            if deferred:
                due = False
            if task and task["status"] == "READY" and not ending:
                due = True
            attempted = False
            financial_started = False
            if due:
                analysis_memory = copy.deepcopy(memory) | {
                    "experiment_id": eid,
                    "session_started_at": at.isoformat(),
                    "participation": a["participation"],
                    "current_valuation": a["snapshot"],
                    "exposure": a["stats"]["exposure"],
                }
                analysis_memory.pop("resolved_forecasts", None)
                try:
                    if task and task["status"] == "READY":
                        if (
                            fingerprint(wallet) != task["wallet_hash"]
                            or (
                                at - datetime.fromisoformat(task["created_at"])
                            ).total_seconds()
                            > SETTINGS["decision_valid_seconds"]
                        ):
                            raise ValueError(
                                "CACHED_DECISION_EXPIRED_OR_PORTFOLIO_CHANGED"
                            )
                        plan = DecisionPlan.model_validate(task["plan"])
                        audit = task.get("audit", {})
                    elif store.reserve_llm(
                        eid,
                        a["id"],
                        cid,
                        at,
                        a["risk"]["calls_per_day"]
                        if SETTINGS.get("session_quotas_enabled", True)
                        else None,
                    ):
                        attempted = True
                        result = reasoner.decide(a, wallet, eligible, analysis_memory)
                        plan = (
                            result
                            if isinstance(result, DecisionPlan)
                            else DecisionPlan(agent_id=a["id"], actions=[result])
                        )
                        audit = copy.deepcopy(getattr(reasoner, "last_audit", {}))
                        task = {
                            "status": "READY",
                            "created_at": at.isoformat(),
                            "wallet_hash": fingerprint(wallet),
                            "plan": plan.model_dump(mode="json"),
                            "audit": audit,
                        }
                        store.task_save(task_id, eid, a["id"], task)
                    else:
                        plan = None
                        audit = {}
                        a["runtime"] = {
                            "status": "QUOTA_LIMIT"
                            if SETTINGS.get("session_quotas_enabled", True)
                            else "SESSION_ALREADY_RESERVED",
                            "at": at.isoformat(),
                            "reason": "Daily session quota or previously reserved session; no duplicate LLM call",
                        }
                    local.update(eligible)
                    markets.update(local)
                    if plan:
                        if plan.agent_id != a["id"]:
                            raise ValueError("WRONG_AGENT")
                        # Network observations happen outside the financial transaction.
                        for d in plan.actions:
                            if (
                                d.action in ("BUY", "SELL")
                                and hasattr(provider, "refresh")
                                and d.market_id in local
                            ):
                                from .providers import Polymarket

                                if isinstance(provider, Polymarket):
                                    provider.refresh(
                                        local[d.market_id],
                                        d.outcome,
                                        for_execution=True,
                                    )
                                else:
                                    provider.refresh(local[d.market_id], d.outcome)
                        at = clock(state, now)
                        if at >= datetime.fromisoformat(state["end_at"]):
                            raise ValueError("Deadline crossed during analysis")
                        financial_started = True
                        with store.locked(eid):
                            memory.pop("needs_policy_review", None)
                            memory.pop("last_failure_at", None)
                            memory["calls"] = memory.get("calls", 0) + int(attempted)
                            memory["last_call"] = at.isoformat()
                            memory["portfolio_changed"] = False
                            memory["reviewed_horizon_markets"] = [
                                m.id
                                for m in local.values()
                                if m.end_at
                                and 0
                                < (m.end_at - at).total_seconds()
                                < (7200 if a["dynamic"] else 21600)
                            ]
                            memory["prices"] = {
                                f"{m.id}:{o}": str(
                                    min(b.asks, key=lambda l: l.price).price
                                )
                                for m in local.values()
                                for o, b in m.books.items()
                                if b.asks
                            }
                            state["markets"].update(
                                {k: v.model_dump(mode="json") for k, v in local.items()}
                            )
                            store.save(state, projection(state))
                            for i, d in enumerate(plan.actions):
                                action_at = clock(state, now)
                                if action_at >= datetime.fromisoformat(state["end_at"]):
                                    event(
                                        store,
                                        state,
                                        "DEADLINE_CUTOFF",
                                        "Remaining planned actions were not executed after the deadline",
                                        a["id"],
                                        {"remaining_actions": len(plan.actions) - i},
                                    )
                                    break
                                record_trade(
                                    store,
                                    state,
                                    a,
                                    wallet,
                                    d,
                                    local,
                                    cid,
                                    str(i),
                                    action_at,
                                )
                            memory["research_memory"] = (
                                memory.get("research_memory", [])
                                + [
                                    {
                                        "at": at.isoformat(),
                                        "market_id": d.market_id,
                                        "action": d.action,
                                        "reason": d.reasoning[:400],
                                    }
                                    for d in plan.actions
                                ]
                            )[-20:]
                            memory["research_failures"] = [
                                {
                                    "tool": t["tool"],
                                    "arguments": t["arguments"],
                                    "at": t["at"],
                                    "error": t.get("result", {}).get("error"),
                                }
                                for t in audit.get("research", [])
                                if not t["ok"]
                            ][-8:]
                            a["last_analysis"] = a["runtime"].copy()
                            if audit:
                                a["stats"]["last_research_quality"] = {
                                    "at": at.isoformat(),
                                    "inspected_candidates": audit.get(
                                        "inspected_candidates", 0
                                    ),
                                    "candidate_target": audit.get("candidate_target"),
                                    "readable_pages": sum(
                                        t["tool"] == "read_web" and t["ok"]
                                        for t in audit.get("research", [])
                                    ),
                                    "failed_tools": sum(
                                        not t["ok"] for t in audit.get("research", [])
                                    ),
                                    "structured_sources": sum(
                                        t["tool"] == "get_public_data" and t["ok"]
                                        for t in audit.get("research", [])
                                    ),
                                }
                                totals = a["stats"].setdefault(
                                    "llm_usage",
                                    {
                                        "sessions": 0,
                                        "requests": 0,
                                        "prompt_tokens": 0,
                                        "completion_tokens": 0,
                                        "cached_prompt_tokens": 0,
                                    },
                                )
                                totals["sessions"] = totals.get("sessions", 0) + 1
                                for k in (
                                    "requests",
                                    "prompt_tokens",
                                    "completion_tokens",
                                    "cached_prompt_tokens",
                                    "cache_write_prompt_tokens",
                                ):
                                    totals[k] = totals.get(k, 0) + audit.get(k, 0)
                                totals["model"] = audit.get("model")
                                totals.setdefault("metering_started_at", at.isoformat())
                                event(
                                    store,
                                    state,
                                    "LLM_USAGE",
                                    "Measured Azure session",
                                    a["id"],
                                    {k: v for k, v in audit.items() if k != "research"},
                                )
                                for t in audit.get("research", []):
                                    event(
                                        store,
                                        state,
                                        "RESEARCH" if t["ok"] else "RESEARCH_ERROR",
                                        t["tool"],
                                        a["id"],
                                        t,
                                    )
                            task["status"] = "COMMITTED"
                            store.task_save(task_id, eid, a["id"], task)
                            store.assert_wallet(eid, a["id"], wallet)
                            a["wallet"] = wallet.model_dump(mode="json")
                            store.save(state, projection(state))
                except Exception as exc:
                    if financial_started:
                        raise
                    # Persistence errors must propagate; provider/validation failures are contained.
                    from openai import OpenAIError
                    from polymarket.errors import PolymarketError
                    import httpx

                    if not isinstance(
                        exc,
                        (
                            ValueError,
                            KeyError,
                            OpenAIError,
                            PolymarketError,
                            httpx.HTTPError,
                        ),
                    ):
                        raise
                    with store.locked(eid):
                        memory.pop("needs_policy_review", None)
                        memory["last_failure_at"] = at.isoformat()
                        memory["last_call"] = at.isoformat()
                        memory["calls"] = memory.get("calls", 0) + int(attempted)
                        a["runtime"] = {
                            "status": "BUDGET_LIMIT"
                            if "AZURE_ESTIMATED_BUDGET_REACHED" in str(exc)
                            else "TECHNICAL_ERROR",
                            "at": at.isoformat(),
                            "reason": type(exc).__name__ + ": " + str(exc)[:160],
                        }
                        a["last_analysis"] = a["runtime"].copy()
                        event(store, state, "ERROR", a["runtime"]["reason"], a["id"])
                        failed_audit = copy.deepcopy(
                            getattr(reasoner, "last_audit", {})
                        )
                        if attempted and failed_audit.get("agent_id") == a["id"]:
                            event(
                                store,
                                state,
                                "LLM_USAGE_ERROR",
                                "Analysis failed; independently metered requests and retrieved evidence retained",
                                a["id"],
                                failed_audit,
                            )
                        store.save(state, projection(state))
            else:
                a["runtime"] = {
                    "status": "ANALYSIS_DEFERRED"
                    if deferred
                    else "CLOSING"
                    if ending
                    else "QUOTA_LIMIT"
                    if provider_ok
                    and SETTINGS.get("session_quotas_enabled", True)
                    and memory.get("calls", 0) >= a["risk"]["calls_per_day"]
                    else "NOT_DUE"
                    if provider_ok
                    else "PROVIDER_ERROR",
                    "at": at.isoformat(),
                    "reason": "Daily UTC session quota reached; valuation and exits continue"
                    if SETTINGS.get("session_quotas_enabled", True)
                    and memory.get("calls", 0) >= a["risk"]["calls_per_day"]
                    else "Interval/event priority; no forced trade",
                }
            refresh_positions(provider, wallet, local)
            markets.update(local)
            with store.locked(eid):
                if hasattr(provider, "refresh"):
                    archive_held_observations(
                        store, state, a, wallet, local, cid, clock(state, now)
                    )
                settlements(
                    store,
                    state,
                    a,
                    wallet,
                    local,
                    clock(state, now),
                    datetime.fromisoformat(state["end_at"])
                    if clock(state, now) >= datetime.fromisoformat(state["end_at"])
                    else None,
                )
                a["wallet"] = wallet.model_dump(mode="json")
                feedback(store, state, a, local, clock(state, now))
                a["participation"] = participation_status(a, at, state["end_at"])
                store.assert_wallet(eid, a["id"], wallet)
                state["inflight"]["completed_agents"].append(a["id"])
                state["updated_at"] = utcnow().isoformat()
                store.save(state, projection(state))
        # A common fresh valuation instant removes the sequential valuation bias.
        for a in state["agents"]:
            refresh_positions(provider, Wallet.model_validate(a["wallet"]), markets)
        at = clock(state, now)
        ending = at >= datetime.fromisoformat(state["end_at"])
        valuation_markets = (
            store.historical_markets(
                eid,
                datetime.fromisoformat(state["end_at"]),
                SETTINGS["closing_max_age_seconds"],
            )
            if ending
            else markets
        )
        if ending:
            valuation_markets.update(
                {
                    k: m
                    for k, m in markets.items()
                    if m.resolved
                    and m.resolved_at
                    and m.resolved_at <= datetime.fromisoformat(state["end_at"])
                }
            )
        with store.locked(eid):
            point = {"at": at.isoformat()}
            for a in state["agents"]:
                v = snapshot(
                    a,
                    valuation_markets,
                    datetime.fromisoformat(state["end_at"]) if ending else at,
                    D(state["fx"]["usd_per_eur"]),
                    SETTINGS["closing_max_age_seconds"] if ending else None,
                    history=state["history"],
                )
                point[a["id"]] = {k: v[k] for k in ("nav_eur", "roi", "complete")}
                store.record(
                    "portfolio_snapshots",
                    id=f"{eid}:{cid}:{a['id']}",
                    experiment_id=eid,
                    agent_id=a["id"],
                    created_at=at.isoformat(),
                    payload=v,
                )
                a["stats"]["performance"] = performance(
                    state["history"] + [point], a["id"]
                )
            state["history"].append(point)
            state["markets"] = {
                k: v.model_dump(mode="json") for k, v in markets.items()
            }
            state["cycles"].append(cid)
            state.setdefault("completed_request_ids", []).extend(
                x
                for x in state["inflight"].get("request_ids", [requested_id])
                if x not in state.get("completed_request_ids", [])
            )
            state.pop("inflight", None)
            state["updated_at"] = utcnow().isoformat()
            if provider_ok:
                state["last_market_sync"] = at.isoformat()
            partial = any(not a["snapshot"]["complete"] for a in state["agents"])
            state["health"] = {
                "last_cycle_id": cid,
                "started_at": started.isoformat(),
                "completed_at": utcnow().isoformat(),
                "duration_seconds": round((utcnow() - started).total_seconds(), 2),
                "market_count": len(markets),
                "market_provider_ok": provider_ok,
                "partial_data": partial,
                "provider_error_count": len(provider.errors),
                "cycle_count": len(state["cycles"]),
                "policy_version": SETTINGS["policy_version"],
                "trigger": os.getenv("GITHUB_EVENT_NAME", "local"),
                "trigger_source": os.getenv("SURVIVAL_TRIGGER_SOURCE", "local"),
            }
            source = state["health"]["trigger_source"]
            if source == "supabase-watchdog":
                state["last_watchdog_cycle"] = state["updated_at"]
            if source == "cloudflare-watchdog":
                state["last_cloudflare_cycle"] = state["updated_at"]
            if state["health"]["trigger"] == "schedule":
                state["last_scheduled_cycle"] = state["updated_at"]
            state["health"].update(
                last_watchdog_cycle=state.get("last_watchdog_cycle"),
                last_scheduled_cycle=state.get("last_scheduled_cycle"),
                last_cloudflare_cycle=state.get("last_cloudflare_cycle"),
            )
            state["health"]["azure_budget"] = store.meter_summary(eid)
            state["health"]["financial_invariants"] = (
                "All ten cash balances reconcile to immutable ledger entries; positions and cash non-negative"
            )
            if os.getenv("GITHUB_RUN_ID"):
                state["health"]["logs_url"] = (
                    f"https://github.com/{os.getenv('GITHUB_REPOSITORY')}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
                )
            if ending:
                from .reporting import final_report

                state["status"] = "CLOSING" if partial else "FINISHED"
                state["report"] = final_report(state, at)
                if not partial:
                    store.record(
                        "final_reports",
                        experiment_id=eid,
                        created_at=at.isoformat(),
                        payload=state["report"],
                    )
                event(
                    store,
                    state,
                    "CLOSING" if partial else "FINISH",
                    "No new decisions; waiting for verifiable deadline valuation"
                    if partial
                    else "Final report saved",
                    details=state["report"],
                )
            store.save(state, projection(state))
            current_held = {
                p["market_id"]
                for a in state["agents"]
                for p in a["wallet"]["positions"].values()
                if D(p["quantity"]) > 0
            }
            for mid, m in markets.items():
                store.record(
                    "market_snapshots",
                    id=f"{eid}:{cid}:{mid}",
                    experiment_id=eid,
                    cycle_id=cid,
                    market_id=mid,
                    created_at=at.isoformat(),
                    payload=archived_market(m, mid in current_held),
                )
            event(
                store,
                state,
                "CYCLE_COMPLETE",
                f"Cycle complete · {len(markets)} markets · {len(state['cycles'])} cycles",
                details=state["health"],
            )
            store.save(state, projection(state))
        return state
