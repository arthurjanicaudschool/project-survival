from types import SimpleNamespace as NS
from decimal import Decimal as D
import pytest
from survival.providers import Polymarket, AzureReasoner
from survival.models import utcnow, Wallet
from survival.agents import definitions
from survival.fixtures import FixtureProvider, FixtureReasoner


@pytest.mark.parametrize(
    "price,yes,no",
    [
        ("0", "0", "1"),
        ("500000000000000000", ".5", ".5"),
        ("1000000000000000000", "1", "0"),
    ],
)
def test_legacy_final_oracle_resolution_without_v2_payout_fields(price, yes, no):
    from survival.models import Position
    from survival.engine import settle

    provider = Polymarket.__new__(Polymarket)
    provider.errors = []
    row = NS(
        status="resolved",
        condition_id="condition",
        payouts=None,
        resolved_at=None,
        price=D(price),
        transaction_hash="0xofficial-resolution",
    )

    def resolutions(**kwargs):
        assert kwargs == {"condition_ids": "condition"}
        return [row]

    provider.client = NS(get_resolutions=resolutions)
    m = NS(
        id="legacy",
        version="v1",
        slug="legacy",
        question="Q",
        description="Rules",
        condition_id="condition",
        events=[],
        category="Tech",
        tags=[],
        metrics=NS(liquidity=0, volume_24hr=0),
        state=NS(active=True, closed=True, accepting_orders=False, end_date=utcnow()),
        resolution=NS(
            source="", question_id="question", uma_resolution_status="resolved"
        ),
        outcomes=NS(
            yes=NS(token_id="yes", price=D(yes)), no=NS(token_id="no", price=D(no))
        ),
    )
    before = utcnow()
    market = provider.normalize(m, include_history=False)
    assert market.resolved and not market.active
    assert market.payouts == {"YES": D(yes), "NO": D(no)}
    assert before <= market.resolved_at <= utcnow()
    assert "observed" in market.resolution_evidence["timestamp_basis"]
    wallet = Wallet(
        initial=10,
        cash=9,
        positions={
            "legacy:NO": Position(market_id="legacy", outcome="NO", quantity=2, cost=1)
        },
    )
    settle(wallet, market)
    assert wallet.cash == 9 + 2 * D(no)
    previous = wallet.cash
    settle(wallet, market)
    assert wallet.cash == previous  # no duplicate settlement


@pytest.mark.parametrize(
    "status,condition,price,gamma_yes",
    [
        ("proposed", "condition", "1000000000000000000", "1"),
        ("resolved", "wrong", "1000000000000000000", "1"),
        ("resolved", "condition", "123", "1"),
        ("resolved", "condition", "1000000000000000000", ".9"),
    ],
)
def test_legacy_resolution_rejects_nonfinal_mismatched_or_uncorroborated_records(
    status, condition, price, gamma_yes
):
    provider = Polymarket.__new__(Polymarket)
    provider.errors = []
    row = NS(
        status=status,
        condition_id=condition,
        payouts=None,
        resolved_at=None,
        price=D(price),
        transaction_hash="tx",
    )

    def missing_book(**kwargs):
        raise ValueError("No book")

    provider.client = NS(
        get_resolutions=lambda **kwargs: [row], get_order_book=missing_book
    )
    m = NS(
        id="legacy",
        version="v1",
        slug="legacy",
        question="Q",
        description="Rules",
        condition_id="condition",
        events=[],
        category="Tech",
        tags=[],
        metrics=NS(liquidity=0, volume_24hr=0),
        state=NS(active=True, closed=True, accepting_orders=False, end_date=utcnow()),
        resolution=NS(source="", question_id="q", uma_resolution_status="resolved"),
        outcomes=NS(
            yes=NS(token_id="yes", price=D(gamma_yes)), no=NS(token_id="no", price=D(0))
        ),
        trading=NS(fees_enabled=False, seconds_delay=0),
    )
    assert not provider.normalize(m, include_history=False).resolved


@pytest.mark.parametrize(
    "version,expected", [("v1", "token-yes"), ("v2", "position-yes")]
)
def test_protocol_identifiers_and_fee_metadata(version, expected, monkeypatch):
    monkeypatch.setattr("survival.providers.time.sleep", lambda _: None)
    provider = Polymarket.__new__(Polymarket)
    provider.errors = []

    class Client:
        def get_order_book(self, asset_id):
            return NS(
                timestamp=utcnow(),
                bids=[NS(price=D(".39"), size=D(30))],
                asks=[NS(price=D(".41"), size=D(30))],
                min_order_size=D(5),
                tick_size=D(".01"),
                hash="observed",
            )

        def list_price_history(self, **kwargs):
            return NS(first_page=lambda: NS(items=[]))

    provider.client = Client()
    m = NS(
        id="123",
        version=version,
        slug="test",
        question="Q?",
        description="Rules",
        condition_id="condition",
        state=NS(active=True, closed=False, accepting_orders=True, end_date=utcnow()),
        resolution=NS(source="https://example.org", uma_resolution_status=None),
        trading=NS(
            fees_enabled=True,
            fee_schedule=NS(rate=D(".07"), exponent=1),
            seconds_delay=0,
        ),
        outcomes=NS(
            yes=NS(token_id="token-yes", position_id="position-yes"),
            no=NS(token_id="token-no", position_id="position-no"),
        ),
        events=[],
        tags=[],
        category="Crypto",
        metrics=NS(liquidity=D(5000), volume_24hr=D(1000)),
    )
    market = provider.normalize(m)
    assert market.assets["YES"] == expected
    assert market.books["YES"].fee_rate == D(".07")
    sleeps = []
    monkeypatch.setattr("survival.providers.time.sleep", sleeps.append)
    provider.client.get_market = lambda **kwargs: m
    m.trading.seconds_delay = 3
    m.trading.fee_schedule = NS(rate=D(".09"), exponent=1)
    provider.refresh(market, "YES", for_execution=True)
    assert (
        3 in sleeps
        and market.books["YES"].fee_rate == D(".09")
        and market.seconds_delay == 3
    )
    m.trading.fee_schedule = None
    with pytest.raises(ValueError, match="Unknown fee"):
        provider.normalize(m)
    m.version = "future"
    with pytest.raises(ValueError, match="Unsupported"):
        provider.normalize(m)


def test_azure_json_and_source_validation_without_network():
    agent = definitions()[0]
    wallet = Wallet(initial=D(11), cash=D(11))
    markets = FixtureProvider(utcnow()).collect()
    d = FixtureReasoner().decide(agent, wallet, markets, {})

    class FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["response_format"] == {"type": "json_object"}
            return NS(choices=[NS(message=NS(content=d.model_dump_json()))])

    azure = AzureReasoner.__new__(AzureReasoner)
    azure.client = NS(chat=NS(completions=FakeCompletions()))
    import os
    from unittest.mock import patch

    with patch.dict(os.environ, {"AZURE_OPENAI_DEPLOYMENT": "test"}):
        assert azure.decide(agent, wallet, markets, {}).agent_id == "A1"
        d.sources = ["https://invented.example/news"]
        with pytest.raises(ValueError, match="unsupported source"):
            azure.decide(agent, wallet, markets, {})
