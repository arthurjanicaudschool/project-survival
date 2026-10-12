import json
from decimal import Decimal as D
from types import SimpleNamespace as NS
import pytest
from survival.agents import definitions
from survival.engine import authorize
from survival.fixtures import FixtureProvider, FixtureReasoner
from survival.models import Wallet, utcnow
from survival.providers import AzureReasoner
from survival.research import ResearchTools, public_url


def test_wait_is_a_choice_not_a_market_rejection():
    agent = definitions()[0]
    d = FixtureReasoner().decide(agent, Wallet(initial=D(10), cash=D(10)), {}, {})
    d.action, d.outcome, d.market_id = "WAIT", None, ""
    assert authorize(agent, Wallet(initial=D(10), cash=D(10)), d, {}, utcnow(), {}) == (None, "", D(0))


@pytest.mark.parametrize("index", [0, 5])
def test_unrestricted_agents_can_invest_full_cash_despite_negative_edge(index):
    a = definitions()[index]
    w = Wallet(initial=D(10), cash=D(10))
    markets = FixtureProvider(utcnow()).collect()
    d = FixtureReasoner().decide(a, w, markets, {})
    d.proposed_stake, d.confidence, d.estimated_probability = D(1000), D(0), D(".01")
    execution, rejection, edge = authorize(a, w, d, markets, utcnow(), {"paused_until": "2099-01-01T00:00:00+00:00"})
    assert not rejection and execution.fills and edge < 0
    assert D("9.99") < execution.gross + execution.fees <= w.cash


def test_prudent_sizing_is_relaxed_but_explicit():
    a = definitions()[2]
    w = Wallet(initial=D(50), cash=D(50))
    markets = FixtureProvider(utcnow()).collect()
    d = FixtureReasoner().decide(a, w, markets, {})
    d.proposed_stake = D(50)
    execution, rejection, _ = authorize(a, w, d, markets, utcnow(), {})
    assert not rejection and execution.gross + execution.fees <= D("17.5")


def test_research_rejects_private_sources(monkeypatch):
    monkeypatch.setattr("survival.research.socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(ValueError):
        public_url("https://example.org/news")
    with pytest.raises(ValueError):
        public_url("http://169.254.169.254/latest/meta-data")


def test_get_market_can_inspect_outside_initial_watchlist():
    market = next(iter(FixtureProvider(utcnow()).collect().values()))
    provider = NS(client=NS(get_market=lambda **kwargs: market), normalize=lambda raw: raw)
    tools = ResearchTools(provider)
    watched = {}
    result = tools.call("get_market", {"reference": "12345"}, watched)
    assert result["market"]["id"] == market.id and market.id in watched
    assert tools.trace[-1]["ok"]


def test_research_failure_is_explicit_and_does_not_add_markets():
    tools = ResearchTools(NS(client=NS()))
    watched = {}
    result = tools.call("get_market", {"reference": "missing"}, watched)
    assert "error" in result and not watched and not tools.trace[-1]["ok"]


def test_search_preserves_opaque_sdk_pagination_cursor():
    seen = []
    cursor = "eyJ2IjoxLCJwIjoyfQ=="
    page = NS(items=[], has_more=False, next_cursor=None)
    paginator = NS(first_page=lambda: page)
    def from_cursor(value):
        seen.append(value)
        return paginator
    paginator.from_cursor = from_cursor
    tools = ResearchTools(NS(client=NS(search=lambda **kwargs: paginator)))
    result = tools.call("search_markets", {"query": "Bitcoin", "cursor": cursor}, {})
    assert "error" not in result and seen == [cursor]


def test_azure_tool_loop_retrieves_market_and_accounts_for_tokens(monkeypatch):
    agent = definitions()[0]
    wallet = Wallet(initial=D(10), cash=D(10))
    market = next(iter(FixtureProvider(utcnow()).collect().values()))
    provider = NS(client=NS(get_market=lambda **kwargs: market), normalize=lambda raw: raw)
    azure = AzureReasoner.__new__(AzureReasoner)
    azure.provider, azure.research, azure.last_audit = provider, ResearchTools(provider), {}
    d = FixtureReasoner().decide(agent, wallet, {}, {})
    class ToolCall:
        type, call_id, name, arguments = "function_call", "one", "get_market", '{"reference":"12345"}'
        def model_dump(self, **kwargs):
            return {"type": self.type, "call_id": self.call_id, "name": self.name, "arguments": self.arguments}
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return NS(model="test-model", usage=NS(input_tokens=100, output_tokens=30, input_tokens_details=None), output=[ToolCall()] if len(calls) == 1 else [], status="completed", output_text=d.model_dump_json())
    azure.responses_client = NS(responses=NS(create=create))
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "test")
    watched = {}
    result = azure.decide(agent, wallet, watched, {})
    assert result.agent_id == "A1" and market.id in watched
    assert calls[0]["tool_choice"] == "required"
    assert azure.last_audit["requests"] == 3
    assert azure.last_audit["prompt_tokens"] == 300
    assert azure.last_audit["research"][0]["ok"]
