"""Offline phase 2 demonstration. Never imported by the live provider."""
from datetime import timedelta
from decimal import Decimal as D
from .fixtures import FixtureProvider, FixtureReasoner
from .models import Decision
from .phase2 import CONFIG


class BetFixtureProvider(FixtureProvider):
    def __init__(self, now, origin=None, resolved=False):
        super().__init__(now)
        self.origin = origin or now
        self.resolved = resolved

    def collect(self, held_ids=()):
        base = super().collect()["fixture-weather"]
        result = {}
        for i, category in enumerate(CONFIG["categories"]):
            m = base.model_copy(deep=True)
            m.id = f"fixture-{category}"
            m.category = category
            m.question = f"DÉMO — Événement fictif de {category} : le résultat sera-t-il Oui ?"
            m.resolution_source = "https://example.com/fixture-only"
            m.url = "https://example.com/fixture-only"
            m.description = "DÉMONSTRATION uniquement. Aucune cotation ou actualité réelle."
            m.end_at = self.origin + timedelta(days=1 if i < 2 else 3)
            if self.resolved and i < 2:
                m.active = False
                m.resolved = True
                m.resolved_at = self.now
                m.payouts = {"YES": D(1 if i == 0 else 0), "NO": D(0 if i == 0 else 1)}
                m.resolution_evidence = {"method": "SYNTHETIC FIXTURE"}
            result[m.id] = m
        return result


class BetFixtureReasoner(FixtureReasoner):
    def decide(self, agent, wallet, markets, memory):
        m = next((m for m in markets.values() if m.category == agent["category"]
                  and not any(p.market_id == m.id for p in wallet.positions.values())), None)
        return Decision(agent_id=agent["id"], market_id=m.id if m else "", outcome="YES" if m else None,
                        action="BUY" if m else "WAIT", estimated_probability=D(".65"), confidence=D(".7"),
                        reasoning="DÉMONSTRATION : choix déterministe inventé pour illustrer une mise et son résultat. Aucun modèle IA ni fait réel n’a été utilisé.",
                        sources=[], proposed_stake=D(20) if m else D(0), expected_edge=D(0),
                        max_buy_price=D(".45") if m else None,
                        exit_plan="Conserver jusqu’au résultat officiel.", risk_factors=["Données fictives de démonstration"])
