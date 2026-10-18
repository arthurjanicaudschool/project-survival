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


def test_rescue_split_preserves_cash_journal_and_closes_fractional_minimum(tmp_path):
    now = utcnow()
    store = Store(demo_path=tmp_path / "rescue.sqlite")
    initialize(store, "test", "demo", {"usd_per_eur": "1.1"}, now)

    class Partial(FixtureProvider):
        def collect(self, *args):
            markets = super().collect()
            markets["fixture-weather"].books["YES"].asks = [
                Level(price=".4", size="4.99")
            ]
            return markets

    class OnlyA3(FixtureReasoner):
        def decide(self, agent, *args):
            d = super().decide(agent, *args)
            if agent["id"] != "A3":
                d.action = "WAIT"
            return d

    before = cycle(store, "test", Partial(now), OnlyA3(), "buy", now)
    a = before["agents"][2]
    assert D(a["wallet"]["positions"]["fixture-weather:YES"]["quantity"]) == D("4.99")

    class Rescue(FixtureProvider):
        def collect(self, *args):
            markets = super().collect()
            markets["fixture-weather"].condition_id = "0x" + "a" * 64
            return markets

    close = now + timedelta(hours=145)
    state = cycle(store, "test", Rescue(close), NoLLM(), "close", close)
    a = state["agents"][2]
    assert all(D(p["quantity"]) == 0 for p in a["wallet"]["positions"].values())
    assert a["orders"][-1]["execution"]["fills"][0]["quantity"] == "5.00"
    assert state["abandoned_positions"][0]["quantity"] == "0.01"
    assert state["abandoned_positions"][0]["not_a_sale_or_resolution"]
    rows = [
        __import__("json").loads(r[0])
        for r in store.db.execute(
            "select payload from audit where kind='ledger_entries'"
        )
    ]
    assert sum(D(r["amount"]) for r in rows if r["agent_id"] == "A3") == D(
        a["wallet"]["cash"]
    )
    assert [(r["kind"], D(r["amount"])) for r in rows if r["kind"] == "SPLIT"] == [
        ("SPLIT", D("-.01"))
    ]
    assert sum(r["kind"] == "ABANDONMENT" for r in rows) == 1
    count = store.db.execute("select count(*) from audit").fetchone()[0]
    cycle(store, "test", Rescue(close), NoLLM(), "close", close)
    assert store.db.execute("select count(*) from audit").fetchone()[0] == count
    store.close()


def test_abandonment_cap_is_on_total_possible_payout_not_cost(tmp_path):
    from survival.closing import abandon_tiny_residues

    store = Store(demo_path=tmp_path / "tiny.sqlite")
    now = utcnow()
    state = initialize(store, "test", "demo", {"usd_per_eur": "1.1"}, now)
    markets = FixtureProvider(now).collect()
    for index in (0, 1):
        a = state["agents"][index]
        w = Wallet(
            initial=10,
            cash=10,
            positions={
                "fixture-weather:YES": Position(
                    market_id="fixture-weather",
                    outcome="YES",
                    quantity=".011",
                    cost=".00001",
                )
            },
        )
        abandon_tiny_residues(store, state, a, w, markets, now)
        assert w.cash == 10
        assert w.positions["fixture-weather:YES"].quantity == (
            0 if index == 0 else D(".011")
        )
    assert sum(D(r["max_foregone_payout"]) for r in state["abandoned_positions"]) == D(
        ".011"
    )
    w.positions["fixture-weather:YES"].quantity = D("4.99")
    abandon_tiny_residues(store, state, a, w, markets, now)
    assert w.positions["fixture-weather:YES"].quantity == D("4.99")
    store.close()


def test_rescue_never_spends_on_stale_or_insufficient_bids(tmp_path):
    from survival.closing import rescue_minimums

    store = Store(demo_path=tmp_path / "no-rescue.sqlite")
    now = utcnow()
    state = initialize(store, "test", "demo", {"usd_per_eur": "1.1"}, now)
    a = state["agents"][0]
    markets = FixtureProvider(now).collect()
    m = markets["fixture-weather"]
    m.condition_id = "0x" + "b" * 64
    m.books["YES"].bids = [Level(price=".38", size="4.99")]
    wallet = Wallet(
        initial=10,
        cash=8,
        positions={
            m.id + ":YES": Position(
                market_id=m.id, outcome="YES", quantity="4.99", cost=2
            )
        },
    )
    rescue_minimums(store, state, a, wallet, markets, "fail", now)
    m.books["YES"].bids = [Level(price=".38", size=100)]
    rescue_minimums(
        store, state, a, wallet, markets, "stale", now + timedelta(minutes=4)
    )
    assert wallet.cash == 8 and len(wallet.positions) == 1
    assert not store.db.execute(
        "select 1 from audit where kind='ledger_entries' and payload like '%SPLIT%'"
    ).fetchone()
    store.close()
