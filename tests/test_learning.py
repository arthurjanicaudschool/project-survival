from decimal import Decimal as D
from datetime import timedelta
import pytest
from survival.learning import build_feedback, accept_reviews
from survival.models import LearningReview, utcnow
from survival.store import Store
from survival.runner import initialize, cycle
from survival.fixtures import FixtureProvider, FixtureReasoner


def journal():
    def order(identifier, kind, q, pnl="0"):
        return {"id": identifier, "kind": kind, "created_at": identifier, "payload": {
            "market_id": "m", "outcome": "NO", "realized_pnl": pnl, "category": "Politics",
            "execution": {"fills": [{"quantity": str(q), "price": ".4", "fee": ".1"}]}}}
    return [order("1", "BUY", 10), order("2", "SELL", 4, "-.2"), {
        "id": "3", "kind": "RESOLUTION", "created_at": "3", "payload": {
            "position": "m:NO", "amount": "6", "pnl": "3.54", "quantity": "6", "payout_per_share": "1", "category": "Politics"}}]


def test_partial_exit_net_results_calibration_and_replay():
    rows = journal()
    decisions = {"1": {"probability_basis": "ESTIMATED", "estimated_probability": ".3", "reasoning": "Thesis"}}
    feedback = build_feedback(rows, decisions, {})
    assert feedback["closed_events"] == 2
    assert (feedback["wins"], feedback["losses"]) == (1, 1)
    assert D(feedback["realized_net_pnl"]) == D("3.34")
    assert D(feedback["execution_fees"]) == D(".2")
    assert feedback["recent_outcomes"][0]["partial_exit"]
    assert feedback["recent_outcomes"][0]["exit_fees"] == "0.1"
    assert feedback["recent_outcomes"][0]["entry_context"][0]["original_entry_fees"] == "0.1"
    assert feedback["open_theses"] == []
    assert feedback["calibration"] == {"resolved_estimates": 1, "brier_score": "0.09"}
    assert feedback == build_feedback(rows, decisions, {}, feedback)
    assert feedback["categories"]["Politics"]["closed_events"] == 2


def test_unestimated_exploration_and_unrealized_are_not_learning_successes():
    feedback = build_feedback(journal()[:1], {"1": {"probability_basis": "UNESTIMATED", "estimated_probability": ".5"}}, {})
    assert feedback["closed_events"] == 0
    assert len(feedback["open_theses"]) == 1
    feedback = build_feedback(journal(), {"1": {"probability_basis": "UNESTIMATED", "estimated_probability": ".5"}}, {})
    assert feedback["calibration"]["resolved_estimates"] == 0
    assert feedback["calibration"]["brier_score"] is None


def test_mixed_entries_preserve_distinct_theses_and_binary_no_resolution():
    rows = journal()
    other_buy = {**rows[0], "id": "1b"}
    rows.insert(1, other_buy)
    rows[-1]["payload"].update(quantity="16", amount="0", payout_per_share="0", pnl="-6.56")
    f = build_feedback(rows, {"1": {"probability_basis": "ESTIMATED", "estimated_probability": ".8"}}, {})
    assert f["recent_outcomes"][-1]["entry_count"] == 2
    assert f["calibration"] == {"resolved_estimates": 1, "brier_score": "0.04"}
    assert f["recent_outcomes"][-1]["resolved_yes"] == "1"


def test_review_requires_own_observed_episode_and_is_bounded():
    f = build_feedback(journal(), {}, {})
    valid = LearningReview(episode_ids=["2"], lesson="Fees mattered; causality uncertain", adaptation="Compare fee-adjusted exits")
    invalid = LearningReview(episode_ids=["another-agent"], lesson="Bad", adaptation="Bad")
    accepted, rejected = accept_reviews(f, [valid, invalid], "now", "decision")
    assert len(accepted) == 1 and rejected == 1
    assert f["reviews"][0]["status"] == "HYPOTHESIS"
    for _ in range(8):
        accept_reviews(f, [valid], "later", "next")
    assert len(f["reviews"]) == 5


def test_full_audit_backfill_and_independent_memory_reaches_reasoner(tmp_path):
    store = Store(demo_path=tmp_path / "state.sqlite")
    now = utcnow()
    initialize(store, "test", "demo", {"usd_per_eur": "1.1"}, now)
    first = cycle(store, "test", FixtureProvider(now), FixtureReasoner(), "first", now)
    assert first["agents"][0]["memory"]["learning"]["open_theses"]
    # Remove bounded dashboard histories: authoritative journal still backfills.
    with store.locked("test"):
        state = store.load("test")
        for a in state["agents"]:
            a["orders"] = []; a["decisions"] = []; a["memory"].pop("learning", None)
        store.save(state, {})
    class InspectReasoner(FixtureReasoner):
        def decide(self, agent, wallet, markets, memory):
            assert "learning" in memory
            for thesis in memory["learning"]["open_theses"]:
                assert all(e["decision_id"].endswith(":" + agent["id"]) for e in thesis["entries"])
            return super().decide(agent, wallet, markets, memory)
    later = now + timedelta(hours=7)
    second = cycle(store, "test", FixtureProvider(later), InspectReasoner(), "second", later)
    assert second["agents"][0]["memory"]["learning"]["open_theses"]
    assert first["end_at"] == second["end_at"]
    assert cycle(store, "test", FixtureProvider(later), InspectReasoner(), "second", later) == second
    store.close()


def test_realized_feedback_is_reviewed_and_saved_in_next_session(tmp_path):
    store = Store(demo_path=tmp_path / "closed.sqlite")
    now = utcnow()
    initialize(store, "test", "demo", {"usd_per_eur": "1.1"}, now)
    cycle(store, "test", FixtureProvider(now), FixtureReasoner(), "buy", now)
    class Seller(FixtureReasoner):
        def decide(self, agent, wallet, markets, memory):
            return super().decide(agent, wallet, markets, memory).model_copy(update={"action": "SELL"})
    later = now + timedelta(hours=7)
    sold = cycle(store, "test", FixtureProvider(later), Seller(), "sell", later)
    assert sold["agents"][0]["memory"]["learning"]["losses"] == 1
    class Reviewer(FixtureReasoner):
        def decide(self, agent, wallet, markets, memory):
            feedback = memory["learning"]
            assert D(feedback["realized_net_pnl"]) == wallet.realized
            episode = feedback["recent_outcomes"][-1]
            return super().decide(agent, wallet, markets, memory).model_copy(update={
                "action": "WAIT", "learning_review": [LearningReview(episode_ids=[episode["id"]],
                    lesson="This exit lost money after execution costs; one observation is insufficient.",
                    adaptation="Inspect spread and fee-adjusted exit depth before the next entry.")]})
    later = now + timedelta(hours=14)
    reviewed = cycle(store, "test", FixtureProvider(later), Reviewer(), "review", later)
    assert all(a["memory"]["learning"]["reviews"] for a in reviewed["agents"])
    assert any(e["kind"] == "LEARNING_REVIEW" for e in reviewed["events"])
    assert reviewed == store.load("test")
    store.close()
