"""Agent-local feedback rebuilt from the immutable financial journal.

No model calls, portfolio mutations or inferred counterfactual returns here.
Replaying the journal also backfills trades made before this feature existed.
"""
from decimal import Decimal as D
from .agents import SETTINGS


def build_feedback(ledger, decisions, markets, previous=None):
    previous = previous or {}
    entries, episodes, categories = {}, [], {}
    wins = losses = flat = calibration_count = 0
    realized = fees = brier = D(0)
    for row in ledger:
        kind, payload = row["kind"], row["payload"]
        if kind not in ("BUY", "SELL", "RESOLUTION"):
            continue
        if kind == "RESOLUTION":
            key = payload["position"]
            mid, outcome = key.rsplit(":", 1)
            held = entries.get(key, [])
            quantity = D(payload["quantity"]) if "quantity" in payload else sum((D(e["remaining_quantity"]) for e in held), D(0))
            pnl = D(payload["pnl"])
            payout = D(payload["payout_per_share"]) if "payout_per_share" in payload else D(payload["amount"]) / quantity if quantity else None
            partial = False
        else:
            mid, outcome = payload["market_id"], payload["outcome"]
            key = f"{mid}:{outcome}"
            fills = (payload.get("execution") or {}).get("fills", [])
            quantity = sum((D(f["quantity"]) for f in fills), D(0))
            paid_fees = sum((D(f["fee"]) for f in fills), D(0))
            fees += paid_fees
            if kind == "BUY":
                decision = decisions.get(row["id"], {})
                entries.setdefault(key, []).append({
                    "decision_id": row["id"], "at": str(row["created_at"]),
                    "remaining_quantity": str(quantity),
                    "reasoning": decision.get("reasoning", "Historical reasoning unavailable")[:400],
                    "decision_kind": payload.get("decision_kind", "STRATEGIC"),
                    "probability_basis": decision.get("probability_basis", "UNAVAILABLE"),
                    "estimated_probability": decision.get("estimated_probability"),
                    "confidence": decision.get("confidence"),
                    "exit_plan": decision.get("exit_plan", "")[:200],
                })
                continue
            held = entries.get(key, [])
            remaining = sum((D(e["remaining_quantity"]) for e in held), D(0))
            partial = quantity < remaining
            pnl = D(payload["realized_pnl"])
            payout = None
        context = [e.copy() for e in held if D(e["remaining_quantity"]) > 0]
        category = payload.get("category", markets.get(mid, {}).get("category", "Unclassified"))
        episode = {
            "id": row["id"], "at": str(row["created_at"]), "market_id": mid,
            "outcome": outcome, "category": category, "event": kind,
            "partial_exit": partial, "quantity": str(quantity), "net_pnl": str(pnl),
            "result": "GAIN" if pnl > 0 else "LOSS" if pnl < 0 else "FLAT",
            "entry_context": context[-SETTINGS["learning"]["entry_context"]:], "entry_count": len(context),
            "exit_reasoning": decisions.get(row["id"], {}).get("reasoning", "Market resolution" if kind == "RESOLUTION" else "Unavailable")[:800],
            "attribution": "Average-cost position; mixed entries cannot be attributed to a single thesis.",
        }
        if kind == "RESOLUTION" and payout in (D(0), D(1)):
            yes_result = payout if outcome == "YES" else 1 - payout
            episode["resolved_yes"] = str(yes_result)
            for entry in context:
                if entry["probability_basis"] == "ESTIMATED" and entry["estimated_probability"] is not None:
                    brier += (D(entry["estimated_probability"]) - yes_result) ** 2
                    calibration_count += 1
        episodes.append(episode)
        realized += pnl
        wins += int(pnl > 0)
        losses += int(pnl < 0)
        flat += int(pnl == 0)
        bucket = categories.setdefault(category, {"closed_events": 0, "net_pnl": "0"})
        bucket["closed_events"] += 1
        bucket["net_pnl"] = str(D(bucket["net_pnl"]) + pnl)
        remaining = sum((D(e["remaining_quantity"]) for e in held), D(0))
        fraction = min(D(1), quantity / remaining) if remaining else D(1)
        for entry in held:
            entry["remaining_quantity"] = str(D(entry["remaining_quantity"]) * (1 - fraction))
        if not partial:
            entries.pop(key, None)
    return {
        "version": 1, "closed_events": len(episodes), "wins": wins, "losses": losses,
        "flat": flat, "realized_net_pnl": str(realized), "execution_fees": str(fees),
        "categories": categories, "recent_outcomes": episodes[-SETTINGS["learning"]["recent_outcomes"]:],
        "open_position_count": len(entries),
        "open_theses": [{"position": k, "entries": v[-SETTINGS["learning"]["entry_context"]:], "entry_count": len(v)} for k, v in entries.items()][-SETTINGS["learning"]["open_theses"]:],
        "calibration": {"resolved_estimates": calibration_count, "brier_score": str(brier / calibration_count) if calibration_count else None},
        "reviews": previous.get("reviews", [])[-SETTINGS["learning"]["reviews"]:],
        "limitations": "Realized results only; partial exits are events, not independent completed trades. Fees include open entries. Small samples do not prove causality. Open positions and WAIT are not successes or failures. Unestimated exploration is excluded from calibration.",
    }


def accept_reviews(feedback, reviews, at, decision_id):
    """Only hypotheses citing this agent's observed outcomes enter memory."""
    known = {e["id"] for e in feedback["recent_outcomes"]}
    accepted, rejected = [], 0
    for review in reviews:
        item = review.model_dump(mode="json")
        if not item["episode_ids"] or not set(item["episode_ids"]) <= known:
            rejected += 1
            continue
        accepted.append(item | {"at": at, "decision_id": decision_id, "status": "HYPOTHESIS"})
    feedback["reviews"] = (feedback.get("reviews", []) + accepted)[-SETTINGS["learning"]["reviews"]:]
    return accepted, rejected
