"""Deterministic, unmistakably synthetic data. Never used in live mode."""

from datetime import timedelta
from decimal import Decimal as D
from .models import Market, Book, Level, Decision


class FixtureProvider:
    errors = []

    def __init__(self, now):
        self.now = now

    def collect(self, held_ids=()):
        m = Market(
            id="fixture-weather",
            slug="fixture-only",
            question="DEMO · Will the fixture resolve YES?",
            description="Synthetic test fixture, not a real Polymarket market.",
            version="v2",
            group="fixture",
            category="Fixture",
            end_at=self.now + timedelta(days=1),
            active=True,
            liquidity=D(5000),
            volume=D(1000),
            assets={"YES": "fixture-yes", "NO": "fixture-no"},
        )
        for o, p in (("YES", D(".40")), ("NO", D(".60"))):
            m.books[o] = Book(
                asset_id=m.assets[o],
                observed_at=self.now,
                bids=[Level(price=p - D(".02"), size=D(100))],
                asks=[Level(price=p, size=D(100))],
                minimum=D(5),
                tick=D(".01"),
                fee_rate=D(".04"),
                evidence="SYNTHETIC",
            )
        return {m.id: m}

    def close(self):
        pass


class FixtureReasoner:
    def decide(self, agent, wallet, markets, memory):
        return Decision(
            agent_id=agent["id"],
            market_id="fixture-weather",
            outcome="YES",
            action="BUY",
            estimated_probability=D(".65"),
            confidence=D(".8"),
            reasoning="DEMO deterministic fixture decision; no LLM used.",
            sources=[],
            proposed_stake=D(3),
            expected_edge=D(".25"),
            exit_plan="Fixture exit",
            risk_factors=["Synthetic data"],
        )
