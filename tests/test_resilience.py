"""Regression coverage for audit findings; deterministic, no paid services."""

import json
from datetime import timedelta
from decimal import Decimal as D
from types import SimpleNamespace as NS
import pytest
from survival.models import (
    utcnow,
    Wallet,
    Position,
    DecisionPlan,
    ExitRules,
    EvidenceClaim,
    Level,
)
from survival.fixtures import FixtureProvider, FixtureReasoner
from survival.engine import execute, apply, valuation, authorize
from survival.agents import definitions, should_reason
from survival.providers import strict_schema, compact_transcript
from survival.evidence import extract, verify_claims
from survival.research import ResearchTools
from survival.runner import initialize, cycle, projection
from survival.runtime import automatic_exits
from survival.store import Store


def test_missing_quote_and_dust_are_unknown_not_losses():
    at = utcnow()
    m = next(iter(FixtureProvider(at).collect().values()))
    w = Wallet(
        initial=10,
        cash=8,
        positions={
            m.id + ":YES": Position(market_id=m.id, outcome="YES", quantity=2, cost=2)
        },
    )
    result = valuation(w, {m.id: m}, at)
    assert not result["complete"] and result["nav"] is None and result["roi"] is None
    assert (
        result["nav_lower_bound"] == "8"
        and result["valuation_details"][0]["reason"] == "BELOW_MARKET_MINIMUM"
    )
    result = valuation(w, {}, at)
    assert result["valuation_details"][0]["reason"] == "MISSING_BOOK"


def test_fak_can_partially_match_below_submitted_minimum():
    at = utcnow()
    b = next(iter(FixtureProvider(at).collect().values())).books["YES"]
    b.asks = [Level(price=".4", size=2)]
    e = execute(b, "BUY", D(3), at)
    assert e.status == "PARTIAL" and e.quantity == 2 and e.quantity < b.minimum


def test_agent_price_bound_and_quantity_close():
    at = utcnow()
    a = definitions()[0]
    markets = FixtureProvider(at).collect()
    m = next(iter(markets.values()))
    w = Wallet(initial=10, cash=10)
    d = FixtureReasoner().decide(a, w, markets, {})
    d.max_buy_price = D(".39")
    assert authorize(a, w, d, markets, at, {})[1] == "PRICE_LIMIT"
    d.max_buy_price = D(".4")
    e, reason, _ = authorize(a, w, d, markets, at, {})
    apply(w, m.id, "YES", "BUY", e)
    d.action = "SELL"
    d.close_position = True
    d.proposed_stake = 0
    d.min_sell_price = D(".37")
    e, reason, edge = authorize(a, w, d, markets, at, {})
    assert not reason and e.quantity == w.positions[m.id + ":YES"].quantity
    assert edge == (e.gross - e.fees) / e.quantity - d.estimated_probability


def test_price_move_does_not_require_fake_resolution_forecast():
    a = definitions()[0]
    w = Wallet(initial=10, cash=10)
    at = utcnow()
    markets = FixtureProvider(at).collect()
    raw = FixtureReasoner().decide(a, w, markets, {}).model_dump()
    raw.update(
        probability_basis="UNESTIMATED",
        estimated_probability=D(".5"),
        confidence=0,
        expected_edge=0,
        thesis_type="PRICE_MOVE",
        target_price=D(".5"),
        horizon_hours=2,
        max_buy_price=D(".41"),
    )
    plan = DecisionPlan.model_validate({"agent_id": a["id"], "actions": [raw]})
    assert authorize(a, w, plan.actions[0], markets, at, {})[2] > 0


def test_empty_script_pages_are_not_successful_research():
    assert (
        extract("<script>" + ("window.test=1; " * 100) + "</script>")["error"]
        == "NO_USABLE_CONTENT"
    )
    text = " ".join(
        ["The official release records the latest observed value and publication date."]
        * 10
    )
    result = extract("<article>" + text + "</article><script>window.test=1;</script>")
    assert result["quality"] == "READABLE" and "window" not in result["excerpt"]
    d = FixtureReasoner().decide(definitions()[0], Wallet(initial=10, cash=10), {}, {})
    d.claims = [
        EvidenceClaim(
            url="https://example.org",
            quote="The official release records",
            claim="Observed publication",
        )
    ]
    trace = [{"ok": True, "result": result | {"url": "https://example.org"}}]
    assert verify_claims([d], trace)[0]["quote_verified"]
    d.claims[0].quote = "Invented sentence never present"
    assert not verify_claims([d], trace)[0]["quote_verified"]


def test_pagination_keeps_all_markets_in_flattened_page():
    raw = [
        NS(
            id=str(i),
            question="Q",
            slug="q",
            state=NS(active=True, accepting_orders=True, end_date=None),
            metrics=NS(liquidity=1, volume_24hr=1),
        )
        for i in range(135)
    ]
    page = NS(items=[NS(events=[NS(markets=raw)])], next_cursor=None)
    tools = ResearchTools(NS(client=NS(search=lambda **k: NS(first_page=lambda: page))))
    found = []
    args = {"query": "Q"}
    while True:
        result = tools.call("search_markets", args, {})
        assert "error" not in result
        found.extend(m["id"] for m in result["markets"])
        if not result["next_cursor"]:
            break
        args = {"query": "Q", "cursor": result["next_cursor"]}
    assert found == [str(i) for i in range(135)]


def test_model_summary_preserves_search_cursor_and_all_ids():
    from survival.providers import compact_tool

    raw = {
        "markets": [
            {
                "id": str(i),
                "question": "q" * 900,
                "slug": "s" * 200,
                "end_at": None,
                "liquidity": "1000",
                "volume_24h": "2",
            }
            for i in range(60)
        ],
        "next_cursor": "opaque",
    }
    result = compact_tool(raw)
    assert result["next_cursor"] == "opaque" and [
        m["id"] for m in result["markets"]
    ] == [str(i) for i in range(60)]
    assert len(json.dumps(result)) < 22000


def test_tracking_summary_preserves_totals_and_bounds_large_histories():
    from survival.providers import compact_tool

    raw = {
        "data": [
            {
                "tracking": {
                    "startDate": "2026-10-01",
                    "endDate": "2026-10-20",
                    "stats": {
                        "total": 123,
                        "pace": 10,
                        "daily": list(range(300)),
                        "cumulative": ["x" * 1000] * 300,
                    },
                }
            }
        ]
    }
    result = compact_tool(raw)
    tracking = result["data"][0]["tracking"]
    assert tracking["stats"]["total"] == 123 and tracking["startDate"] == "2026-10-01"
    assert (
        len(tracking["stats"]["daily"]) == 14 and "cumulative" not in tracking["stats"]
    )
    assert "cumulative" in raw["data"][0]["tracking"]["stats"]


def test_strict_schema_requires_nullable_fields_and_no_extra_properties():
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node.get("properties", {}))
            assert "default" not in node
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(strict_schema()["schema"])


def test_generated_trades_need_agent_price_bounds_and_allow_wait():
    from survival.providers import validate_generated_plan

    d = FixtureReasoner().decide(definitions()[0], Wallet(initial=10, cash=10), {}, {})
    d.max_buy_price = None
    with pytest.raises(ValueError, match="max_buy_price"):
        validate_generated_plan(d.model_dump_json(), "A1", set(), [])
    d.action = "WAIT"
    d.outcome = None
    assert (
        validate_generated_plan(d.model_dump_json(), "A1", set(), [])[0]
        .actions[0]
        .action
        == "WAIT"
    )


def test_context_compaction_preserves_json_and_cursor():
    messages = [
        {
            "type": "function_call_output",
            "output": json.dumps(
                {
                    "markets": [
                        {"id": str(i), "question": "Q", "description": "x" * 100}
                        for i in range(60)
                    ],
                    "next_cursor": "opaque",
                }
            ),
        }
    ]
    compact_transcript(messages, 4000)
    result = json.loads(messages[0]["output"])
    assert result["next_cursor"] == "opaque" and len(result["markets"]) == 60


def test_catalogue_features_compact_before_aborting_final_decision():
    body = {
        "initial_watchlist_not_a_whitelist": [
            {
                "id": str(i),
                "question": "Q",
                "features": {
                    "YES": {
                        "ask": ".4",
                        "minimum_entry_cost": "2",
                        "momentum_absolute": "x" * 700,
                    }
                },
            }
            for i in range(24)
        ],
        "portfolio": {"cash": "10"},
    }
    messages = [
        {"role": "user", "content": json.dumps(body)},
        {
            "type": "function_call_output",
            "output": json.dumps(
                {
                    "excerpt": "words " * 1000,
                    "url": "https://example.org",
                    "quality": "READABLE",
                }
            ),
        },
    ]
    compact_transcript(messages, 7000)
    reduced = json.loads(messages[0]["content"])
    assert [m["id"] for m in reduced["initial_watchlist_not_a_whitelist"]] == [
        str(i) for i in range(24)
    ]
    assert reduced["portfolio"]["cash"] == "10"


def test_valuation_bounds_only_include_remaining_unsellable_quantity():
    at = utcnow()
    m = next(iter(FixtureProvider(at).collect().values()))
    wallet = Wallet(
        initial=10,
        cash=7,
        positions={
            m.id + ":YES": Position(
                market_id=m.id, outcome="YES", quantity=D("6.001"), cost=3
            )
        },
    )
    result = valuation(wallet, {m.id: m}, at)
    assert D(result["nav_upper_bound"]) - D(result["nav_lower_bound"]) == D(".001")
    assert result["valuation_details"][0]["reason"] == "INPUT_PRECISION_DUST"


def test_legacy_unknown_marks_do_not_become_historical_losses():
    from survival.analytics import observed_drawdown, performance
    from survival.runner import make_state

    state = make_state("test", "demo", {"usd_per_eur": "1.1"}, utcnow())
    state["history"].append(
        {
            "at": utcnow().isoformat(),
            **{
                a["id"]: {"nav_eur": "0", "roi": "-1", "stranded": ["missing"]}
                for a in state["agents"]
            },
        }
    )
    public = projection(state)
    assert public["history"][-1]["A1"]["roi"] is None
    agent = state["agents"][0]
    observed_drawdown(agent, state["history"], D(11), D("1.1"))
    assert D(agent["stats"]["max_drawdown"]) == 0
    assert performance(state["history"], "A1")["incomplete_samples"] == 1


def test_opaque_reasoning_envelope_does_not_consume_visible_evidence_budget():
    messages = [
        {"role": "user", "content": "Evidence"},
        {"type": "reasoning", "encrypted_content": "opaque" * 30000},
        {"type": "function_call", "call_id": "one", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "one", "output": "{}"},
    ]
    compact_transcript(messages, 500)
    assert len(messages[1]["encrypted_content"]) == 180000
    assert messages[2]["call_id"] == messages[3]["call_id"]


def test_event_trigger_and_technical_retry_respect_daily_quota():
    at = utcnow().replace(hour=12)
    risk = definitions()[0]["risk"]
    markets = FixtureProvider(at).collect()
    memory = {
        "day": at.date().isoformat(),
        "calls": 1,
        "last_call": at.isoformat(),
        "prices": {"fixture-weather:YES": ".3"},
    }
    assert should_reason(
        memory, list(markets.values()), at + timedelta(minutes=10), risk
    )
    memory.update(prices={}, last_failure_at=at.isoformat())
    assert not should_reason(
        memory, list(markets.values()), at + timedelta(minutes=10), risk
    )
    assert should_reason(
        memory, list(markets.values()), at + timedelta(minutes=15), risk
    )
    memory["calls"] = 12
    assert not should_reason(
        memory, list(markets.values()), at + timedelta(hours=3), risk
    )


def test_structured_exit_without_new_llm():
    at = utcnow()
    markets = FixtureProvider(at).collect()
    m = next(iter(markets.values()))
    a = definitions()[0]
    w = Wallet(
        initial=10,
        cash=7,
        positions={
            m.id + ":YES": Position(
                market_id=m.id,
                outcome="YES",
                quantity=6,
                cost=3,
                exit_rules=ExitRules(stop_bid=D(".39")),
            )
        },
    )
    exits = list(automatic_exits(a, w, markets, at))
    assert (
        len(exits) == 1 and exits[0][1].close_position and exits[0][1].action == "SELL"
    )


def test_cached_decision_survives_financial_crash_without_second_llm(tmp_path):
    store = Store(demo_path=tmp_path / "crash.sqlite")
    at = utcnow()
    initialize(store, "test", "demo", {"usd_per_eur": "1.1"}, at)
    calls = []

    class Count:
        def decide(self, a, *args):
            calls.append(a["id"])
            return FixtureReasoner().decide(a, *args)

    original = store.record

    def crash(table, **columns):
        if table == "simulated_fills":
            raise RuntimeError("Power loss")
        original(table, **columns)

    store.record = crash
    with pytest.raises(RuntimeError):
        cycle(store, "test", FixtureProvider(at), Count(), "first", at)
    assert calls == ["A1"] and store.task_get("test:first:A1")["status"] == "READY"
    store.record = original
    state = cycle(store, "test", FixtureProvider(at), Count(), "retry", at)
    assert calls.count("A1") == 1 and state["cycles"] == ["first"]
    count = store.db.execute("select count(*) from audit").fetchone()[0]
    assert cycle(store, "test", FixtureProvider(at), Count(), "retry", at) == state
    assert store.db.execute("select count(*) from audit").fetchone()[0] == count
    for a in state["agents"]:
        store.assert_wallet("test", a["id"], Wallet.model_validate(a["wallet"]))
    store.close()


def test_lease_blocks_other_cycles_without_long_transaction(tmp_path):
    first = Store(demo_path=tmp_path / "lease.sqlite")
    second = Store(demo_path=tmp_path / "lease.sqlite")
    with first.lease("same"):
        assert not first.db.in_transaction
        with pytest.raises(RuntimeError):
            with second.lease("same"):
                pass
    first.close()
    second.close()


def test_deadline_snapshot_uses_past_book_only_and_unknown_closing_recovers(tmp_path):
    at = utcnow()
    store = Store(demo_path=tmp_path / "close.sqlite")
    state = initialize(store, "test", "demo", {"usd_per_eur": "1.1"}, at)
    mid = "fixture-weather"
    end = at + timedelta(hours=168)
    a = state["agents"][0]
    a["wallet"]["positions"][mid + ":YES"] = Position(
        market_id=mid, outcome="YES", quantity=6, cost=0
    ).model_dump(mode="json")
    store.save(state, projection(state))

    class NoLLM:
        def decide(self, *args):
            raise AssertionError("No decision after deadline")

    state = cycle(
        store,
        "test",
        FixtureProvider(end + timedelta(minutes=1)),
        NoLLM(),
        "missing-close",
        end + timedelta(minutes=1),
    )
    assert state["status"] == "CLOSING" and state["report"]["roi_winner"] is None
    assert not store.db.execute(
        "select 1 from audit where kind='final_reports'"
    ).fetchone()
    m = next(iter(FixtureProvider(end - timedelta(minutes=1)).collect().values()))
    store.record(
        "market_snapshots",
        id="recovered",
        experiment_id="test",
        created_at=(end - timedelta(seconds=30)).isoformat(),
        payload=m.model_dump(mode="json"),
    )
    state = cycle(
        store,
        "test",
        FixtureProvider(end + timedelta(minutes=2)),
        NoLLM(),
        "recovered-close",
        end + timedelta(minutes=2),
    )
    assert (
        state["status"] == "FINISHED"
        and state["report"]["valuation_time"] == end.isoformat()
    )
    assert D(state["agents"][0]["snapshot"]["nav"]) > D(a["wallet"]["cash"])
    store.close()


def test_cash_ties_do_not_select_agent_id_as_fake_winner(tmp_path):
    at = utcnow()
    s = Store(demo_path=tmp_path / "tie.sqlite")
    initialize(s, "test", "demo", {"usd_per_eur": "1.1"}, at)
    state = cycle(
        s,
        "test",
        FixtureProvider(at),
        FixtureReasoner(),
        "end",
        at + timedelta(hours=168),
    )
    assert (
        state["report"]["roi_winner"] is None
        and len(state["report"]["roi_winners"]) == 10
    )
    s.close()


def test_deadline_crossed_between_plan_actions_stops_remaining_trades(
    tmp_path, monkeypatch
):
    import survival.runtime as runtime

    at = utcnow()
    s = Store(demo_path=tmp_path / "mid-plan.sqlite")
    state = initialize(s, "test", "demo", {"usd_per_eur": "1.1"}, at)
    clock = [at]
    original = runtime.record_trade

    def trade(*args, **kwargs):
        result = original(*args, **kwargs)
        clock[0] = at + timedelta(hours=168)
        return result

    monkeypatch.setattr(runtime, "clock", lambda *args: clock[0])
    monkeypatch.setattr(runtime, "record_trade", trade)

    class Plan:
        def decide(self, a, w, markets, memory):
            d = FixtureReasoner().decide(a, w, markets, memory)
            return DecisionPlan(agent_id=a["id"], actions=[d, d.model_copy()])

    state = cycle(s, "test", FixtureProvider(at), Plan(), "cutoff", at)
    assert sum(a["stats"]["trades"] for a in state["agents"]) == 1
    assert any(e["kind"] == "DEADLINE_CUTOFF" for e in state["events"])
    s.close()
