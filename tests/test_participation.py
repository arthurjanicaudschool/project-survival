from datetime import timedelta
from decimal import Decimal as D
from types import SimpleNamespace as NS
import pytest
from pydantic import ValidationError
from survival.agents import definitions
from survival.engine import authorize
from survival.models import Wallet, utcnow, Decision
from survival.fixtures import FixtureProvider, FixtureReasoner
from survival.participation import candidates, status
from survival.providers import AzureReasoner
from survival.research import ResearchTools


def affordable(now):
    markets = FixtureProvider(now).collect()
    market = next(iter(markets.values()))
    market.books["YES"].asks[0].price = D(".20")
    market.books["YES"].bids[0].price = D(".18")
    return markets, market


def exploration(agent, wallet, markets, stake):
    raw = FixtureReasoner().decide(agent, wallet, markets, {}).model_dump()
    return Decision.model_validate(raw | {"decision_kind":"EXPLORATION", "probability_basis":"UNESTIMATED",
        "estimated_probability":D(".5"),"confidence":D(0),"expected_edge":D(0),"proposed_stake":D(stake)})


def test_exactly_hunters_and_sprinters_have_participation_rule():
    assert [a["id"] for a in definitions() if a["risk"].get("participation_required")] == ["A1","A2","A6","A7"]


def test_exploration_previews_respect_fees_minimum_budget_and_research_scope():
    now = utcnow(); agent = definitions()[0]; wallet = Wallet(initial=D(10),cash=D(10))
    markets, market = affordable(now)
    assert not candidates(agent,wallet,markets,set(),now,{})
    options = candidates(agent,wallet,markets,{market.id},now,{})
    assert options
    for option in options:
        assert D(option["preview_quantity"]) >= D(option["minimum_quantity"])
        assert D(option["preview_cost"]) <= D(option["budget_including_fees"]) <= D(2)
    assert not candidates(agent,wallet,markets,{market.id},now+timedelta(minutes=4),{})
    wallet.cash=D(".01")
    assert not candidates(agent,wallet,markets,{market.id},now,{})


def test_exploration_cannot_spend_all_cash_or_repeat_after_first_fill():
    now=utcnow();agent=definitions()[0];wallet=Wallet(initial=D(50),cash=D(50))
    markets, _ = affordable(now)
    decision=exploration(agent,wallet,markets,100)
    execution,rejection,_=authorize(agent,wallet,decision,markets,now,{})
    assert not rejection and execution.gross+execution.fees <= D(10)
    agent["stats"]={"trades":1}
    assert authorize(agent,wallet,decision,markets,now,{})[1] == "PARTICIPATION_ALREADY_FULFILLED"


def test_unestimated_probability_cannot_claim_an_edge():
    now=utcnow();agent=definitions()[0];wallet=Wallet(initial=D(10),cash=D(10))
    markets,_=affordable(now)
    raw=exploration(agent,wallet,markets,1.1).model_dump()
    with pytest.raises(ValidationError):
        Decision.model_validate(raw | {"expected_edge":D(".2")})


def test_rule_deadline_and_fulfilment_are_explicit():
    now=utcnow();agent=definitions()[0]
    agent.update(memory={"participation_started_at":now.isoformat()},stats={"trades":0})
    end=(now+timedelta(days=7)).isoformat()
    assert status(agent,now,end)["deadline"] == (now+timedelta(hours=24)).isoformat()
    assert status(agent,now+timedelta(hours=25),end)["status"] == "OVERDUE"
    agent["stats"]["trades"]=1
    assert status(agent,now+timedelta(hours=25),end)["status"] == "FULFILLED"


def test_pending_agent_is_reprompted_if_it_waits_despite_executable_own_market(monkeypatch):
    now=utcnow();agent=definitions()[0];wallet=Wallet(initial=D(10),cash=D(10))
    markets,market=affordable(now)
    provider=NS(client=NS(get_market=lambda **kwargs:market),normalize=lambda raw:raw)
    azure=AzureReasoner.__new__(AzureReasoner)
    azure.provider,azure.research,azure.last_audit=provider,ResearchTools(provider),{}
    wait=FixtureReasoner().decide(agent,wallet,markets,{}).model_copy(update={"action":"WAIT","outcome":None})
    buy=exploration(agent,wallet,markets,"1.1")
    class Call:
        type,call_id,name,arguments="function_call","one","get_market",'{"reference":"12345"}'
        def model_dump(self,**kwargs):
            return {"type":self.type,"call_id":self.call_id,"name":self.name,"arguments":self.arguments}
    calls=[]
    def create(**kwargs):
        calls.append(kwargs)
        return NS(model="test",usage=None,status="completed",output=[Call()] if len(calls)==1 else [],
                  output_text=(buy if len(calls)==4 else wait).model_dump_json())
    azure.responses_client=NS(responses=NS(create=create))
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT","test")
    decision=azure.decide(agent,wallet,{}, {"participation":{"pending":True}})
    assert decision.action=="BUY" and decision.decision_kind=="EXPLORATION"
    assert azure.last_audit["participation"]["correction_calls"]==1 and len(calls)==4
