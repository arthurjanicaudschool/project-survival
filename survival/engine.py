"""Immediate-or-cancel fills against observed depth. Pure Decimal accounting."""

from decimal import Decimal as D, ROUND_DOWN, ROUND_HALF_UP, ROUND_UP
from .models import Execution, Fill, Position, ZERO, position_key


def fee(quantity, price, book):
    # Per-market parameters; current documented formula exponent=1.
    return (
        quantity * book.fee_rate * (price * (1 - price)) ** book.fee_exponent
    ).quantize(D("0.00001"), rounding=ROUND_HALF_UP)


def execute(
    book,
    side,
    budget,
    now,
    max_age=180,
    slippage=D("0.03"),
    quantity_cap=None,
    enforce_minimum=True,
    limit_price=None,
    requested_quantity=None,
):
    def reject(reason):
        return Execution(status="REJECTED", reason=reason)

    age = (now - book.observed_at).total_seconds()
    if age < -5 or age > max_age:
        return reject("STALE_BOOK")
    if budget <= 0:
        return reject("ZERO_BUDGET")
    levels = sorted(
        book.asks if side == "BUY" else book.bids,
        key=lambda l: l.price,
        reverse=side == "SELL",
    )
    if not levels:
        return reject("NO_LIQUIDITY")
    best = levels[0].price
    # Conservative FAK limit-order convention: submitted share size has two
    # decimals, as in the unified SDK rounding table. Never round up into cash
    # or liquidity that is not available. Matching is a paper approximation.
    quantum = D("0.01")
    if limit_price is not None:
        limit_price = (limit_price / book.tick).to_integral_value(
            rounding=ROUND_DOWN if side == "BUY" else ROUND_UP
        ) * book.tick
    # Minimum constrains the submitted order, not every partial FAK match.
    intended = (
        requested_quantity
        if requested_quantity is not None
        else min(quantity_cap, budget / best)
        if quantity_cap is not None
        else (budget + D(".000005") if side == "BUY" else budget)
        / (
            best
            + (
                book.fee_rate * (best * (1 - best)) ** book.fee_exponent
                if side == "BUY"
                else ZERO
            )
        )
    )
    intended = intended.quantize(quantum, rounding=ROUND_DOWN)
    if enforce_minimum and intended < book.minimum:
        return reject("BELOW_MARKET_MINIMUM")
    remaining, cap, fills = (
        budget,
        min(quantity_cap, intended) if quantity_cap is not None else intended,
        [],
    )
    for level in levels:
        if limit_price is not None and (
            (side == "BUY" and level.price > limit_price)
            or (side == "SELL" and level.price < limit_price)
        ):
            break
        if abs(level.price - best) > slippage:
            break
        if level.price % book.tick != 0:
            return reject("INVALID_TICK_IN_BOOK")
        unit = (
            level.price
            + book.fee_rate * (level.price * (1 - level.price)) ** book.fee_exponent
            if side == "BUY"
            else level.price
        )
        q = min(
            level.size,
            (remaining + D(".000005") if side == "BUY" else remaining) / unit,
        )
        if cap is not None:
            q = min(q, cap)
        q = q.quantize(quantum, rounding=ROUND_DOWN)
        # Rounding per match may exceed the rounded unit fee estimate.
        while (
            q > 0
            and side == "BUY"
            and q * level.price + fee(q, level.price, book) > remaining
        ):
            excess = q * level.price + fee(q, level.price, book) - remaining
            q -= max(
                quantum,
                (excess / level.price).quantize(quantum, rounding=ROUND_UP),
            )
        if q <= 0:
            break
        f = Fill(price=level.price, quantity=q, fee=fee(q, level.price, book))
        fills.append(f)
        remaining -= q * level.price + (f.fee if side == "BUY" else ZERO)
        if cap is not None:
            cap -= q
        if remaining < D("0.00001") or cap == 0:
            break
    if not fills:
        return reject(
            "PRICE_LIMIT" if limit_price is not None else "NO_EXECUTABLE_LIQUIDITY"
        )
    return Execution(
        status="FILLED" if remaining < D("0.00001") or cap == 0 else "PARTIAL",
        fills=fills,
    )


def apply(wallet, market_id, outcome, side, execution):
    if not execution.fills:
        return ZERO
    key = position_key(market_id, outcome)
    position = wallet.positions.get(key, Position(market_id=market_id, outcome=outcome))
    q, gross, fees = execution.quantity, execution.gross, execution.fees
    if side == "BUY":
        if gross + fees > wallet.cash:
            raise ValueError("Insufficient cash")
        wallet.cash -= gross + fees
        position.quantity += q
        position.cost += gross + fees
        realized = ZERO
    else:
        if q > position.quantity:
            raise ValueError("No short selling")
        basis = (
            position.cost
            if q == position.quantity
            else position.cost * q / position.quantity
        )
        realized = gross - fees - basis
        wallet.cash += gross - fees
        position.quantity -= q
        position.cost -= basis
        wallet.realized += realized
    wallet.positions[key] = position
    return realized


def settle(wallet, market):
    entries = []
    if (
        not market.resolved
        or set(market.payouts) != {"YES", "NO"}
        or sum(market.payouts.values()) != 1
    ):
        return entries
    for key, p in wallet.positions.items():
        if p.market_id == market.id and p.quantity > 0:
            payout = p.quantity * market.payouts[p.outcome]
            pnl = payout - p.cost
            wallet.cash += payout
            wallet.realized += pnl
            entries.append(
                {
                    "position": key,
                    "amount": str(payout),
                    "pnl": str(pnl),
                    "quantity": str(p.quantity),
                    "payout_per_share": str(market.payouts[p.outcome]),
                    "category": market.category,
                }
            )
            p.quantity, p.cost = ZERO, ZERO
    return entries


def value(wallet, markets, now, max_age=180):
    available, stranded, invested = wallet.cash, [], ZERO
    for key, p in wallet.positions.items():
        if p.quantity == 0:
            continue
        m = markets.get(p.market_id)
        b = m.books.get(p.outcome) if m else None
        invested += p.cost
        if (
            m
            and m.resolved
            and set(m.payouts) == {"YES", "NO"}
            and m.resolved_at
            and m.resolved_at <= now
        ):
            available += p.quantity * m.payouts[p.outcome]
            continue
        if m and not m.active and not m.resolved:
            stranded.append(key)
            continue
        if b is None:
            stranded.append(key)
            continue
        e = execute(b, "SELL", D("1e30"), now, max_age, D(1), p.quantity, True)
        available += e.gross - e.fees
        if e.quantity < p.quantity:
            stranded.append(key)
    return available, invested, stranded


def valuation(wallet, markets, now, max_age=180):
    lower, cost, stranded = value(wallet, markets, now, max_age)
    details = []
    unknown_quantity = ZERO
    economic_unliquidated = ZERO
    unknown = []
    for key in stranded:
        p = wallet.positions[key]
        m = markets.get(p.market_id)
        b = m.books.get(p.outcome) if m else None
        sold = (
            execute(b, "SELL", D("1e30"), now, max_age, D(1), p.quantity, True).quantity
            if b and m.active
            else ZERO
        )
        remaining = p.quantity - sold
        economic_unliquidated += remaining
        reason = (
            "MISSING_BOOK"
            if not b
            else "MARKET_NOT_ACCEPTING_ORDERS"
            if m and not m.active
            else "STALE_BOOK"
            if (now - b.observed_at).total_seconds() > max_age
            or (now - b.observed_at).total_seconds() < -5
            else "BELOW_MARKET_MINIMUM"
            if p.quantity < b.minimum
            else "INPUT_PRECISION_DUST"
            if 0 < remaining < D(".01")
            else "INSUFFICIENT_DEPTH"
        )
        known_zero = reason in ("BELOW_MARKET_MINIMUM", "INPUT_PRECISION_DUST")
        if not known_zero:
            unknown.append(key)
            unknown_quantity += remaining
        details.append(
            {
                "position": key,
                "reason": reason,
                "quantity": str(p.quantity),
                "unliquidated_quantity": str(remaining),
                "liquidatable_zero": known_zero,
                "cost": str(p.cost),
                "observed_at": b.observed_at.isoformat() if b else None,
            }
        )
    complete = not unknown
    return {
        "complete": complete,
        "nav_lower_bound": str(lower),
        "nav_upper_bound": str(lower + unknown_quantity),
        "economic_upper_bound": str(lower + economic_unliquidated),
        "unknown_positions": unknown,
        "nav": str(lower) if complete else None,
        "roi": str(lower / wallet.initial - 1) if complete else None,
        "invested_cost": str(cost),
        "stranded": stranded,
        "valuation_details": details,
        "valuation": "Observed immediately liquidatable bids after fees; observed minimum/precision residues contribute zero liquidatable cash, not zero economic value"
        if complete
        else "INCOMPLETE: unknown value; lower bound is not a measured loss",
    }


def authorize(agent, wallet, decision, markets, now, memory, *, liquidation=False):
    if agent.get("phase") == 2:
        from .phase2 import authorize as authorize_bet
        return authorize_bet(agent, wallet, decision, markets, now, memory)
    from .agents import SETTINGS

    if decision.agent_id != agent["id"]:
        return None, "WRONG_AGENT", ZERO
    if decision.action not in ("BUY", "SELL"):
        return None, "", ZERO
    m = markets.get(decision.market_id)
    if not m or not m.active or m.resolved or decision.outcome not in m.books:
        return None, "MARKET_UNAVAILABLE", ZERO
    book = m.books[decision.outcome]
    risk = agent["risk"]
    nav, _, _ = value(wallet, markets, now, SETTINGS["max_age_seconds"])
    key = position_key(m.id, decision.outcome)
    p = wallet.positions.get(key)
    budget = decision.proposed_stake
    if liquidation and decision.action == "BUY":
        return None, "COMPETITION_WIND_DOWN", ZERO
    cap = p.quantity if p else ZERO
    if decision.action == "SELL":
        if decision.sell_quantity is not None:
            if not p or decision.sell_quantity > p.quantity:
                return None, "NO_SHORT_SELLING", ZERO
            cap = decision.sell_quantity
            budget = D("1e30")
        elif decision.close_position:
            budget = D("1e30")
    if decision.action == "BUY":
        if risk.get("prudence_enabled", True) and memory.get("paused_until"):
            from datetime import datetime

            if now < datetime.fromisoformat(memory["paused_until"]):
                return None, "DRAWDOWN_COOLDOWN", ZERO
        group_cost = sum(
            (
                pos.cost
                for pos in wallet.positions.values()
                if pos.market_id in markets and markets[pos.market_id].group == m.group
            ),
            ZERO,
        )
        budget = min(budget, wallet.cash)
        if decision.decision_kind == "EXPLORATION":
            if not risk.get("participation_required", False):
                return None, "EXPLORATION_NOT_ENABLED", ZERO
            if agent.get("stats", {}).get("trades", 0) > 0 or memory.get(
                "participation_fulfilled_at"
            ):
                return None, "PARTICIPATION_ALREADY_FULFILLED", ZERO
            budget = min(budget, wallet.initial * D(risk["exploration_max_fraction"]))
        if risk.get("prudence_enabled", True):
            position_limit = nav * D(risk["max_position_fraction"])
            # A small prudent account can explicitly choose one real minimum
            # instead of being unable to trade at all. No automatic stake raise.
            if agent.get("initial_eur") == "10" and book.asks:
                ask = min(l.price for l in book.asks)
                minimum_cost = book.minimum * ask + fee(book.minimum, ask, book)
                if (
                    position_limit
                    < minimum_cost
                    <= nav * D(SETTINGS["small_account_minimum_fraction"])
                ):
                    position_limit = minimum_cost
            budget = min(
                budget,
                wallet.cash - nav * D(risk["cash_reserve_fraction"]),
                position_limit - (p.cost if p else ZERO),
                nav * D(risk["max_group_fraction"]) - group_cost,
            )
        cap = None
    e = execute(
        book,
        decision.action,
        budget,
        now,
        SETTINGS["max_age_seconds"],
        D(1)
        if liquidation and decision.action == "SELL"
        else D(risk.get("max_slippage", SETTINGS["max_slippage"])),
        cap,
        limit_price=decision.max_buy_price
        if decision.action == "BUY"
        else decision.min_sell_price,
        requested_quantity=cap
        if decision.action == "SELL"
        and (decision.close_position or decision.sell_quantity is not None)
        else None,
    )
    if not e.fills:
        return e, e.reason, ZERO
    probability = (
        decision.estimated_probability
        if decision.outcome == "YES"
        else 1 - decision.estimated_probability
    )
    edge = (
        probability - (e.gross + e.fees) / e.quantity
        if decision.action == "BUY"
        else (e.gross - e.fees) / e.quantity - probability
    )
    if (
        decision.action == "BUY"
        and decision.thesis_type == "PRICE_MOVE"
        and decision.target_price is not None
    ):
        target_fee = (
            book.fee_rate
            * (decision.target_price * (1 - decision.target_price)) ** book.fee_exponent
        )
        edge = decision.target_price - target_fee - (e.gross + e.fees) / e.quantity
    if (
        decision.action == "BUY"
        and risk.get("prudence_enabled", True)
        and (
            edge < D(SETTINGS["min_edge"])
            or decision.confidence < D(SETTINGS["min_confidence"])
        )
    ):
        return None, "INSUFFICIENT_VERIFIED_EDGE", edge
    return e, "", edge
