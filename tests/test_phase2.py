from collections import Counter
from datetime import timedelta
from decimal import Decimal as D
import copy
import json
import pytest
from survival.models import utcnow, Wallet
from survival.store import Store
from survival.runner import cycle, initialize
from survival.engine import authorize, apply
from survival.phase2 import definitions, start, prepare, eligible, CONFIG, market_category
from survival.phase2_fixtures import BetFixtureProvider, BetFixtureReasoner


@pytest.fixture
def setup(tmp_path):
    store = Store(demo_path=tmp_path / "bets.sqlite")
    now = utcnow()
    start(store, "phase2-test", {"usd_per_eur": "1.1"}, now)
    yield store, now
    store.close()


def test_equal_capital_and_specialties(setup):
    store, now = setup
    state = store.load("phase2-test")
    assert len(state["agents"]) == 10
    assert Counter(a["category"] for a in state["agents"]) == {k: 2 for k in CONFIG["categories"]}
    assert sum(D(a["initial_eur"]) for a in state["agents"]) == 1000
    assert len({a["prompt"] for a in definitions()}) == 10
    a, b = state["agents"][:2]
    a["wallet"]["cash"] = "1"
    assert b["wallet"]["cash"] == "110.0"
    assert a["risk"] == b["risk"]


def test_prepare_requires_explicit_start(tmp_path):
    store = Store(demo_path=tmp_path / "ready.sqlite")
    state = prepare(store, "survival-002", mode="demo")
    assert state["status"] == "READY" and state["started_at"] is None
    class Never:
        def collect(self,*a): raise AssertionError("no market request before START")
        def decide(self,*a): raise AssertionError("no Azure before START")
    assert cycle(store, "survival-002", Never(), Never()) == state
    assert store.db.execute("select count(*) from audit").fetchone()[0] == 0
    initialize(store, "survival-002", "demo", {"usd_per_eur":"1.1"})
    assert store.load("survival-002")["status"] == "RUNNING"
    with pytest.raises(ValueError): initialize(store, "survival-002", "demo", {"usd_per_eur":"1.1"})
    store.close()


@pytest.mark.parametrize("change,reason", [
    ({"action":"SELL"},"HOLD_TO_RESOLUTION_ONLY"),
    ({"action":"HOLD"},"HOLD_TO_RESOLUTION_ONLY"),
    ({"thesis_type":"PRICE_MOVE", "target_price":".8", "horizon_hours":12},"EVENT_FORECAST_REQUIRED"),
    ({"exit_rules":{"stop_bid":".2"}},"EVENT_FORECAST_REQUIRED"),
    ({"proposed_stake":"111"},"PRICE_OR_CASH_CONSTRAINT"),
    ({"agent_id":"A2"},"WRONG_AGENT"),
])
def test_python_boundary_rejects_forbidden_bets(setup,change,reason):
    store, now = setup
    a=store.load("phase2-test")["agents"][0]; w=Wallet.model_validate(a["wallet"])
    markets=BetFixtureProvider(now).collect()
    d=BetFixtureReasoner().decide(a,w,markets,{})
    # Validate model-shaped JSON before reaching the execution boundary.
    from survival.models import Decision
    d=Decision.model_validate(d.model_dump(mode="json") | change)
    e,rejection,_=authorize(a,w,d,markets,now,{})
    assert e is None and rejection == reason


def test_only_own_category_before_cutoff_and_no_reentry(setup):
    store,now=setup; a=store.load("phase2-test")["agents"][0]
    w=Wallet.model_validate(a["wallet"]); markets=BetFixtureProvider(now).collect()
    d=BetFixtureReasoner().decide(a,w,markets,{})
    m=markets[d.market_id]; original=m.end_at
    m.end_at=now+timedelta(days=7)
    assert authorize(a,w,d,markets,now,{})[1] == "OUTSIDE_CATEGORY_OR_WEEK"
    m.end_at=original; m.category="Weather"
    assert authorize(a,w,d,markets,now,{})[1] == "OUTSIDE_CATEGORY_OR_WEEK"
    m.category="Politics"
    e,reason,edge=authorize(a,w,d,markets,now,{})
    assert not reason and e.fills and edge != d.expected_edge
    apply(w,m.id,d.outcome,"BUY",e)
    d.outcome="NO"
    assert authorize(a,w,d,markets,now,{})[1] == "BET_ALREADY_PLACED"
    # Settled markets remain in own position history and cannot be bet again.
    for p in w.positions.values(): p.quantity=D(0);p.cost=D(0)
    assert authorize(a,w,d,markets,now,{})[1] == "BET_ALREADY_PLACED"


def test_offline_cycle_cash_locked_learning_and_idempotence(setup):
    store,now=setup
    state=cycle(store,"phase2-test",BetFixtureProvider(now),BetFixtureReasoner(),"one",now)
    assert all(len(a["bets"])==1 for a in state["agents"])
    assert all(a["snapshot"]["nav"] is None and a["snapshot"]["pending_bets"]==1 for a in state["agents"])
    count=store.db.execute("select count(*) from audit").fetchone()[0]
    same=cycle(store,"phase2-test",BetFixtureProvider(now),BetFixtureReasoner(),"one",now)
    assert same==state
    assert count==store.db.execute("select count(*) from audit").fetchone()[0]
    calls=[]
    class Inspect(BetFixtureReasoner):
        def decide(self,a,w,m,memory):
            calls.append(copy.deepcopy(memory))
            return super().decide(a,w,m,memory)
    later=now+timedelta(days=2)
    state=cycle(store,"phase2-test",BetFixtureProvider(later,now,True),Inspect(),"two",later)
    assert calls and all(m["action_history"] for m in calls)
    assert state["agents"][0]["bets"][0]["status"] == "SETTLED"
    assert D(state["agents"][0]["wallet"]["realized"])>0
    assert D(state["agents"][2]["wallet"]["realized"])<0
    assert state["agents"][0]["memory"]["learning"]["closed_events"] == 1
    for a in state["agents"]:
        store.assert_wallet("phase2-test",a["id"],Wallet.model_validate(a["wallet"]))
    assert not any(json.loads(r[0]).get("kind")=="SELL" for r in store.db.execute("select payload from audit where kind='ledger_entries'"))


def test_no_early_sale_or_ai_after_betting_deadline(setup):
    store,now=setup
    first=cycle(store,"phase2-test",BetFixtureProvider(now),BetFixtureReasoner(),"first",now)
    class Never:
        def decide(self,*a): raise AssertionError("no decisions after cutoff")
    for hours in [145,169]:
        at=now+timedelta(hours=hours)
        state=cycle(store,"phase2-test",BetFixtureProvider(at,now),Never(),str(hours),at)
        assert all(a["wallet"]==b["wallet"] for a,b in zip(state["agents"],first["agents"]))
    assert state["status"]=="CLOSING" and state["report"] is None
    assert sum(len(a["bets"]) for a in state["agents"])==10


def test_crash_does_not_duplicate_committed_bet(setup):
    store,now=setup
    original=store.record
    triggered=[False]
    def crash_once(table,**cols):
        if table=="simulated_fills" and not triggered[0]:
            triggered[0]=True
            raise RuntimeError("power loss")
        original(table,**cols)
    store.record=crash_once
    with pytest.raises(RuntimeError):cycle(store,"phase2-test",BetFixtureProvider(now),BetFixtureReasoner(),"one",now)
    assert store.load("phase2-test")["agents"][0]["wallet"]["cash"] == "110.0"
    store.record=original
    state=cycle(store,"phase2-test",BetFixtureProvider(now),BetFixtureReasoner(),"recovery-new-workflow",now)
    assert sum(len(a["bets"]) for a in state["agents"])==10
    assert state["cycles"] == ["phase2-test:one"]


@pytest.mark.parametrize("question,supplied,tags,expected", [
    ("Will X win the election?","",[],"Politics"),
    ("Will X win?","",["Sports","Soccer"],"Sports"),
    ("Highest temperature in Paris?","",[],"Weather"),
    ("Bitcoin above 100k?","",[],"Crypto"),
    ("US CPI this Friday?","",[],"Economics"),
    ("Which AI model?","",[],"Other"),
])
def test_category_matching(question,supplied,tags,expected):
    assert market_category(question,supplied,tags)[0]==expected


def test_finished_only_after_all_official_results(setup):
    store,now=setup
    cycle(store,"phase2-test",BetFixtureProvider(now),BetFixtureReasoner(),"buy",now)
    class AllResolved(BetFixtureProvider):
        def collect(self,held_ids=()):
            markets=super().collect(held_ids)
            for m in markets.values():
                m.resolved=True;m.active=False;m.payouts={"YES":D(1),"NO":D(0)};m.resolved_at=self.now
            return markets
    class Never:
        def decide(self,*args):raise AssertionError("no final LLM")
    at=now+timedelta(hours=170)
    result=cycle(store,"phase2-test",AllResolved(at,now),Never(),"settle",at)
    assert result["status"]=="FINISHED"
    assert len(result["report"]["roi_winners"])==10
    assert result["report"]["roi_winner"] is None
    assert all(a["snapshot"]["pending_bets"]==0 and a["snapshot"]["nav"] for a in result["agents"])


def test_phase2_schema_has_no_trading_actions():
    from survival.providers import strict_schema
    props=strict_schema(2)["schema"]["$defs"]["Decision"]["properties"]
    assert props["action"]["enum"]==["BUY","WAIT"]
    assert props["exit_rules"]=={"type":"null"}
    assert "SELL" in strict_schema()["schema"]["$defs"]["Decision"]["properties"]["action"]["enum"]


def test_phase2_model_has_seen_rules_before_buy(setup):
    from survival.providers import validate_generated_plan
    store, now=setup
    a=store.load("phase2-test")["agents"][0]
    w=Wallet.model_validate(a["wallet"])
    markets=BetFixtureProvider(now).collect()
    decision=BetFixtureReasoner().decide(a,w,markets,{})
    with pytest.raises(ValueError,match="Inspect rules"):
        validate_generated_plan(decision.model_dump_json(),a["id"],set(),[],phase=2)
    trace=[{"tool":"get_market","ok":True,"result":{"market":{"id":decision.market_id}}}]
    assert validate_generated_plan(decision.model_dump_json(),a["id"],set(),trace,phase=2)[0].actions[0].market_id==decision.market_id
