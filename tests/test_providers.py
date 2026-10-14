from types import SimpleNamespace as NS
from decimal import Decimal as D
import pytest
from survival.providers import Polymarket, AzureReasoner
from survival.models import utcnow, Wallet
from survival.agents import definitions
from survival.fixtures import FixtureProvider, FixtureReasoner


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
