from datetime import timedelta
from decimal import Decimal as D
import pytest
from survival.models import Wallet, utcnow, Decision
from survival.fixtures import FixtureProvider
from survival.engine import execute, fee, apply, settle, value, authorize
from survival.agents import definitions


@pytest.fixture
def market():
    return next(iter(FixtureProvider(utcnow()).collect().values()))


def test_current_fee_curve(market):
    b = market.books["YES"]
    assert fee(D(100), D(".5"), b) == D("1.00000")
    assert fee(D(100), D(".3"), b) == fee(D(100), D(".7"), b)
    b.fee_rate = D(0)
    assert fee(D(100), D(".5"), b) == 0


def test_buy_cash_invariant_and_no_mid_price(market):
    b = market.books["YES"]
    w = Wallet(initial=D(10), cash=D(10))
    e = execute(b, "BUY", D(3), utcnow())
    assert e.fills and all(f.price == D(".40") for f in e.fills)
    apply(w, market.id, "YES", "BUY", e)
    assert w.cash >= 0
    assert w.cash + e.gross + e.fees == 10
    assert w.positions[f"{market.id}:YES"].cost == e.gross + e.fees


def test_sell_pnl_and_resolution(market):
    b = market.books["YES"]
    w = Wallet(initial=D(10), cash=D(10))
    buy = execute(b, "BUY", D(3), utcnow())
    apply(w, market.id, "YES", "BUY", buy)
    sale = execute(b, "SELL", D("1e10"), utcnow(), quantity_cap=buy.quantity)
    pnl = apply(w, market.id, "YES", "SELL", sale)
    assert pnl == sale.gross - sale.fees - buy.gross - buy.fees
    assert w.cash == 10 + pnl
    buy = execute(market.books["NO"], "BUY", D(4), utcnow())
    apply(w, market.id, "NO", "BUY", buy)
    market.resolved = True
    market.payouts = {"YES": D(0), "NO": D(1)}
    before = w.cash
    assert len(settle(w, market)) == 1
    assert w.cash == before + buy.quantity
    assert settle(w, market) == []


def test_stale_minimum_partial_tick(market):
    b = market.books["YES"]
    assert execute(b, "BUY", D(1), utcnow()).reason == "BELOW_MARKET_MINIMUM"
    assert (
        execute(b, "BUY", D(10), utcnow() + timedelta(minutes=10)).reason
        == "STALE_BOOK"
    )
    assert execute(b, "BUY", D(100), utcnow()).status == "PARTIAL"
    b.tick = D(".03")
    assert execute(b, "BUY", D(10), utcnow()).reason == "INVALID_TICK_IN_BOOK"


def test_no_leverage_or_short(market):
    w = Wallet(initial=D(1), cash=D(1))
    e = execute(market.books["YES"], "BUY", D(3), utcnow())
    with pytest.raises(ValueError):
        apply(w, market.id, "YES", "BUY", e)
    with pytest.raises(ValueError):
        apply(w, market.id, "YES", "SELL", e)
    assert w.cash == 1


def test_zero_liquidity_lower_bound(market):
    w = Wallet(initial=D(10), cash=D(10))
    e = execute(market.books["YES"], "BUY", D(3), utcnow())
    apply(w, market.id, "YES", "BUY", e)
    market.books["YES"].bids = []
    nav, invested, stranded = value(w, {market.id: market}, utcnow())
    assert nav == w.cash and invested > 0 and stranded


def test_probability_no_is_complement_and_model_edge_untrusted(market):
    from survival.fixtures import FixtureReasoner

    agent = definitions()[5]
    w = Wallet(initial=D(55), cash=D(55))
    d = FixtureReasoner().decide(agent, w, {}, {})
    d.outcome = "NO"
    d.estimated_probability = D(".9")
    d.expected_edge = D(100)
    d.proposed_stake = D(5)
    e, reason, edge = authorize(agent, w, d, {market.id: market}, utcnow(), {})
    # An unrestricted agent can knowingly accept negative edge; the estimate
    # must still be independently recalculated rather than trusting 100.
    assert e is not None and e.fills and reason == "" and edge < 0
    assert abs(edge - (D(".1") - (e.gross + e.fees) / e.quantity)) < D(".000001")


def test_json_validation():
    with pytest.raises(ValueError):
        Decision.model_validate({"agent_id": "A1", "action": "EXECUTE_REAL_ORDER"})


def test_frozen_fx_accounting():
    rate = D("1.123456")
    initial = D(10) * rate
    assert initial / rate == 10
    assert ((initial + D("1.25")) / rate - D(10)).quantize(D(".00000001")) == (
        D("1.25") / rate
    ).quantize(D(".00000001"))


@pytest.mark.parametrize("budget", ["2.00001", "2.04801", "3.01234", "10", "55"])
def test_rounding_never_overspends(market, budget):
    e = execute(market.books["YES"], "BUY", D(budget), utcnow())
    assert e.gross + e.fees <= D(budget)
