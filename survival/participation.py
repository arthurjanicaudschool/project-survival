"""Disclosed first-investment obligation; the model still selects the market."""
from datetime import datetime, timedelta
from decimal import Decimal as D
from .agents import SETTINGS
from .models import Decision, ZERO
from .engine import execute, authorize


class ParticipationContractError(ValueError):
    pass


def status(agent, now, end_at):
    required = agent["risk"].get("participation_required", False)
    start = agent["memory"].get("participation_started_at")
    fulfilled = agent["stats"].get("trades", 0) > 0
    deadline = min(datetime.fromisoformat(end_at), datetime.fromisoformat(start) + timedelta(hours=SETTINGS["participation"]["deadline_hours"])) if start else None
    return {"required": required, "pending": required and not fulfilled,
        "status": "DISCRETIONARY" if not required else "FULFILLED" if fulfilled else "OVERDUE" if deadline and now >= deadline else "PENDING",
        "started_at": start, "deadline": deadline.isoformat() if deadline else None,
        "fulfilled_at": agent["memory"].get("participation_fulfilled_at"),
        "target_fraction": agent["risk"].get("exploration_target_fraction"),
        "max_fraction": agent["risk"].get("exploration_max_fraction")}


def candidates(agent, wallet, markets, inspected_ids, now, memory):
    """Exact order previews, not fills. Only markets researched by this agent."""
    if not agent["risk"].get("participation_required"):
        return []
    cap = min(wallet.cash, wallet.initial * D(agent["risk"]["exploration_max_fraction"]))
    target = wallet.initial * D(agent["risk"]["exploration_target_fraction"])
    result = []
    for mid in inspected_ids:
        market = markets.get(mid)
        if not market or not market.active or market.resolved:
            continue
        for outcome, book in market.books.items():
            minimum = execute(book, "BUY", cap, now, SETTINGS["max_age_seconds"],
                D(agent["risk"]["max_slippage"]), book.minimum)
            if not minimum.fills:
                continue
            budget = min(cap, max(target, minimum.gross + minimum.fees + D("0.00002")))
            preview = Decision(agent_id=agent["id"],market_id=mid,outcome=outcome,action="BUY",
                estimated_probability=D("0.5"), confidence=ZERO, reasoning="Executable preview only; no probability forecast",
                sources=[],proposed_stake=budget,expected_edge=ZERO,exit_plan="Preview only",risk_factors=[],
                decision_kind="EXPLORATION",probability_basis="UNESTIMATED")
            execution, rejection, _ = authorize(agent,wallet,preview,markets,now,memory)
            if rejection or not execution or not execution.fills:
                continue
            result.append({"market_id": mid,"question": market.question,"outcome": outcome,
                "budget_including_fees": str(budget), "preview_cost": str(execution.gross+execution.fees),
                "preview_quantity": str(execution.quantity),"minimum_quantity":str(book.minimum),
                "url":market.url,"book_observed_at":book.observed_at.isoformat(),
                "notice":"Observed executable preview only. No expected return is asserted. Book refreshed again before execution."})
    return result
