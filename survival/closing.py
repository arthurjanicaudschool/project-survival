"""Paper-only full-set conversions and bounded competition abandonment.

No signer, wallet, authenticated client or real order path is used here.
"""

from decimal import Decimal as D

from .agents import SETTINGS
from .models import Position
from .engine import authorize

PROTOCOL_SOURCE = "https://docs.polymarket.com/trading/positions/manage"


def rescue_minimums(store, state, agent, wallet, markets, cid, at):
    from .runtime import liquidation_exits, record_trade
    from .runner import event

    for key, p in list(wallet.positions.items()):
        m = markets.get(p.market_id)
        b = m.books.get(p.outcome) if m else None
        if not m or not m.active or m.resolved or not m.condition_id or not b:
            continue
        gap = b.minimum - p.quantity
        if not (
            p.quantity > 0 and D(0) < gap <= D(SETTINGS["closing_split_max_collateral"])
        ):
            continue
        if gap > wallet.cash or gap % D(".000001") or m.seconds_delay:
            continue
        if set(m.assets) != {"YES", "NO"} or m.version not in ("v1", "v2"):
            continue
        trial = wallet.model_copy(deep=True)
        trial.cash -= gap
        # A full set costs one collateral unit; equal cost allocation has no
        # effect on total P&L and is recorded explicitly rather than a price.
        for outcome in ("YES", "NO"):
            k = f"{m.id}:{outcome}"
            pos = trial.positions.setdefault(
                k, Position(market_id=m.id, outcome=outcome)
            )
            pos.quantity += gap
            pos.cost += gap / 2
        decisions = [
            d for k, d in liquidation_exits(agent, trial, markets, at) if k == key
        ]
        if not decisions:
            continue
        decision = decisions[0]
        preview, rejected, _ = authorize(
            agent, trial, decision, markets, at, agent["memory"], liquidation=True
        )
        if rejected or not preview or preview.quantity != b.minimum:
            continue
        identifier = f"{state['id']}:{cid}:{agent['id']}:split:{key}"
        payload = {
            "market_id": m.id,
            "condition_id": m.condition_id,
            "collateral": str(gap),
            "yes_quantity": str(gap),
            "no_quantity": str(gap),
            "cost_allocation": "Equal halves; accounting allocation, not market prices",
            "protocol_source": PROTOCOL_SOURCE,
            "simulation_method": "Paper full-set conversion: one unit collateral creates equal YES and NO. No onchain transaction; no network gas modeled.",
            "execution_origin": "COMPETITION_LIQUIDATION",
        }
        store.record(
            "ledger_entries",
            id=identifier,
            experiment_id=state["id"],
            agent_id=agent["id"],
            kind="SPLIT",
            amount=str(-gap),
            created_at=at.isoformat(),
            payload=payload,
        )
        wallet.cash, wallet.positions = trial.cash, trial.positions
        event(
            store,
            state,
            "SPLIT",
            "Paper complete-set conversion to reach the real sale minimum",
            agent["id"],
            payload,
        )
        record_trade(
            store,
            state,
            agent,
            wallet,
            decision,
            markets,
            cid,
            "rescue:" + key,
            at,
            liquidation=True,
        )
        if wallet.positions[key].quantity != 0:
            raise RuntimeError(
                "Rescue sale did not fully execute; rollback conversion and sale"
            )


def abandon_tiny_residues(store, state, agent, wallet, markets, at):
    from .runner import event

    records = state.setdefault("abandoned_positions", [])
    used = sum((D(r["max_foregone_payout"]) for r in records), D(0))
    maximum = D(SETTINGS["closing_abandonment_max_payout"])
    for key, p in wallet.positions.items():
        m = markets.get(p.market_id)
        b = m.books.get(p.outcome) if m else None
        if not m or not m.active or m.resolved or not b:
            continue
        if not 0 <= (at - b.observed_at).total_seconds() <= SETTINGS["max_age_seconds"]:
            continue
        # The cap is on the maximum possible payout, not the current price or
        # cost. No material or unknown position can be swept into this rule.
        if not (0 < p.quantity < b.minimum and used + p.quantity <= maximum):
            continue
        entry = {
            "agent_id": agent["id"],
            "position": key,
            "market_id": m.id,
            "quantity": str(p.quantity),
            "cost": str(p.cost),
            "realized_pnl": str(-p.cost),
            "max_foregone_payout": str(p.quantity),
            "at": at.isoformat(),
            "cash_delta": "0",
            "not_a_sale_or_resolution": True,
            "reason": "User-requested competition closure: voluntarily exclude this unsellable paper claim. Zero proceeds, no invented price, fill or real token burn.",
        }
        store.record(
            "ledger_entries",
            id=f"{state['id']}:{agent['id']}:abandon:{key}",
            experiment_id=state["id"],
            agent_id=agent["id"],
            kind="ABANDONMENT",
            amount="0",
            created_at=at.isoformat(),
            payload=entry,
        )
        wallet.realized -= p.cost
        used += p.quantity
        p.quantity, p.cost = D(0), D(0)
        records.append(entry)
        event(
            store,
            state,
            "ABANDONMENT",
            "Non-cash competition abandonment of an unsellable fraction; not a trade",
            agent["id"],
            entry,
        )
