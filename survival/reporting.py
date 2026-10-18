from decimal import Decimal as D
from .agents import SETTINGS


def final_report(state, now):
    known = sorted(
        (a for a in state["agents"] if a["snapshot"].get("complete")),
        key=lambda a: (-D(a["snapshot"]["roi"]), int(a["id"][1:])),
    )
    unknown = [a for a in state["agents"] if not a["snapshot"].get("complete")]
    best = D(known[0]["snapshot"]["roi"]) if known else None
    tied = [
        a["id"] for a in known if abs(D(a["snapshot"]["roi"]) - best) <= D("0.00000001")
    ]
    absolute = max(
        (D(a["snapshot"]["nav"]) - D(a["wallet"]["initial"]) for a in known),
        default=None,
    )
    absolute_ties = [
        a["id"]
        for a in known
        if D(a["snapshot"]["nav"]) - D(a["wallet"]["initial"]) == absolute
    ]
    ranking = []
    for a in known + unknown:
        snap = a["snapshot"]
        roi = D(snap["roi"]) if snap["complete"] else None
        ranking.append(
            {
                "agent_id": a["id"],
                "rank": 1
                + sum(D(x["snapshot"]["roi"]) > roi + D("0.00000001") for x in known)
                if roi is not None
                else None,
                "roi": snap["roi"],
                "profit_eur": str(D(snap["nav_eur"]) - D(a["initial_eur"]))
                if snap["complete"]
                else None,
                "survives": roi > D(SETTINGS["survival_roi"])
                if roi is not None
                else None,
                "stranded": snap["stranded"],
                "return_over_max_drawdown": str(roi / D(a["stats"]["max_drawdown"]))
                if roi is not None and D(a["stats"]["max_drawdown"]) > 0
                else None,
                "trades": a["stats"]["trades"],
                "exploration_trades": a["stats"].get("exploration_trades", 0),
                "participation": a.get("participation"),
                "performance": a["stats"].get("performance"),
                "exposure": a["stats"].get("exposure"),
            }
        )
    strategies = {
        name: [
            r
            for r in ranking
            if next(a for a in state["agents"] if a["id"] == r["agent_id"])["name"]
            == name
        ]
        for name in {a["name"] for a in state["agents"]}
    }
    return {
        "generated_at": now.isoformat(),
        "wind_down": state.get("wind_down"),
        "abandoned_positions": state.get("abandoned_positions", []),
        "abandoned_max_payout": str(
            sum(
                (
                    D(r["max_foregone_payout"])
                    for r in state.get("abandoned_positions", [])
                ),
                D(0),
            )
        ),
        "remaining_positions": [
            {
                "agent_id": a["id"],
                "market_id": p["market_id"],
                "outcome": p["outcome"],
                "quantity": p["quantity"],
                "cost": p["cost"],
            }
            for a in state["agents"]
            for p in a["wallet"]["positions"].values()
            if D(p["quantity"]) > 0
        ],
        "deadline": state["end_at"],
        "valuation_time": state["end_at"],
        "valuation_method": "Last verifiable observation at or before deadline, maximum age 15 minutes. No post-deadline price lookahead; missing data stays unknown.",
        "close_delay_seconds": max(
            0,
            (
                now - __import__("datetime").datetime.fromisoformat(state["end_at"])
            ).total_seconds(),
        ),
        "ranking": ranking,
        "roi_winner": tied[0] if len(tied) == 1 and not unknown else None,
        "roi_winners": tied if not unknown else [],
        "absolute_winner": absolute_ties[0]
        if len(absolute_ties) == 1 and not unknown
        else None,
        "absolute_winners": absolute_ties if not unknown else [],
        "incomplete_valuation": bool(unknown),
        "unranked_agents": [a["id"] for a in unknown],
        "strategies": strategies,
        "strategy_summary": {
            name: {
                "observed_agents": len(rows),
                "valid_agents": sum(r["roi"] is not None for r in rows),
                "mean_roi": str(
                    sum((D(r["roi"]) for r in rows if r["roi"] is not None), D(0))
                    / len(rows)
                )
                if all(r["roi"] is not None for r in rows)
                else None,
                "survivors": sum(r["survives"] is True for r in rows),
                "comparison": "Exploratory comparison only: two agents, different market choices, exposure and capital; policy changed during the experiment.",
            }
            for name, rows in strategies.items()
        },
        "policy_history": state.get("policy_history", []),
        "diversity": __import__("survival.analytics", fromlist=["diversity"]).diversity(
            state["agents"]
        ),
        "benchmarks": {
            "cash_roi": "0",
            "meaning": "Cash preservation is a legitimate benchmark, not evidence of forecasting skill.",
        },
        "limitation": "No proof of future profitability. Ties are explicit; no winner is claimed while any agent is unranked. Research hypotheses are not trained model weights.",
    }
