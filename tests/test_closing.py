from datetime import timedelta
from decimal import Decimal as D

from survival.models import utcnow, Wallet, Position, Level
from survival.fixtures import FixtureProvider, FixtureReasoner
from survival.runner import initialize, cycle
from survival.runtime import liquidation_exits
from survival.engine import authorize
from survival.agents import definitions
from survival.store import Store


class NoLLM:
    def decide(self, *args):
        raise AssertionError("Wind-down must never invoke an AI")


def test_wind_down_sells_existing_holdings_and_rerun_is_idempotent(tmp_path):
    store = Store(demo_path=tmp_path / "close.sqlite")
    now = utcnow()
    initialize(store, "test", "demo", {"usd_per_eur": "1.1"}, now)
    before = cycle(store, "test", FixtureProvider(now), FixtureReasoner(), "buy", now)
    trades = sum(a["stats"]["trades"] for a in before["agents"])
    close = now + timedelta(hours=145)
    state = cycle(store, "test", FixtureProvider(close), NoLLM(), "liquidate", close)
    assert state["wind_down"]["no_new_purchases"]
    assert all(a["runtime"]["status"] == "WIND_DOWN" for a in state["agents"])
    assert all(
        all(D(p["quantity"]) == 0 for p in a["wallet"]["positions"].values())
        for a in state["agents"]
    )
    assert sum(a["stats"]["trades"] for a in state["agents"]) == trades * 2
    sells = [o for a in state["agents"] for o in a["orders"] if o["action"] == "SELL"]
    assert sells and all(
        o["execution_origin"] == "COMPETITION_LIQUIDATION" for o in sells
    )
    count = store.db.execute("select count(*) from audit").fetchone()[0]
    cycle(store, "test", FixtureProvider(close), NoLLM(), "liquidate", close)
    assert store.db.execute("select count(*) from audit").fetchone()[0] == count
    final = cycle(
        store,
        "test",
        FixtureProvider(now + timedelta(hours=168)),
        NoLLM(),
        "end",
        now + timedelta(hours=168),
    )
    assert final["status"] == "FINISHED" and not final["report"]["incomplete_valuation"]
    store.close()


def test_liquidation_uses_deep_bids_but_respects_minimum_staleness_and_cash():
    now = utcnow()
    a = definitions()[2]
    markets = FixtureProvider(now).collect()
    m = markets["fixture-weather"]
    book = m.books["YES"]
    book.bids = [Level(price=".38", size=5), Level(price=".10", size=5)]
    wallet = Wallet(
        initial=10,
        cash=6,
        positions={
            m.id + ":YES": Position(market_id=m.id, outcome="YES", quantity=10, cost=4)
        },
    )
    d = list(liquidation_exits(a, wallet, markets, now))[0][1]
    ordinary, _, _ = authorize(a, wallet, d, markets, now, {})
    close, reason, _ = authorize(a, wallet, d, markets, now, {}, liquidation=True)
    assert ordinary.quantity == 5 and close.quantity == 10 and not reason
    assert close.gross == D("2.40") and wallet.cash == 6
    buy = FixtureReasoner().decide(a, wallet, markets, {})
    assert (
        authorize(a, wallet, buy, markets, now, {}, liquidation=True)[1]
        == "COMPETITION_WIND_DOWN"
    )
    assert (
        authorize(
            a, wallet, d, markets, now + timedelta(minutes=4), {}, liquidation=True
        )[1]
        == "STALE_BOOK"
    )
    wallet.positions[m.id + ":YES"].quantity = D("4.99")
    assert list(liquidation_exits(a, wallet, markets, now)) == []
    assert wallet.positions[m.id + ":YES"].quantity == D("4.99")


def test_wind_down_does_not_hide_unavailable_quotes(tmp_path):
    now = utcnow()
    store = Store(demo_path=tmp_path / "outage.sqlite")
    initialize(store, "test", "demo", {"usd_per_eur": "1.1"}, now)
    before = cycle(store, "test", FixtureProvider(now), FixtureReasoner(), "buy", now)

    class Down:
        errors = []

        def collect(self, *args):
            raise ConnectionError("provider down")

    state = cycle(store, "test", Down(), NoLLM(), "outage", now + timedelta(hours=145))
    assert state["wind_down"] and state["health"]["partial_data"]
    assert [a["wallet"] for a in state["agents"]] == [
        a["wallet"] for a in before["agents"]
    ]
    assert not state["agents"][0]["snapshot"]["complete"]
    store.close()
