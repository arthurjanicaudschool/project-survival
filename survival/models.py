from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

D = Decimal
ZERO = D("0")


def utcnow():
    return datetime.now(timezone.utc)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Level(Model):
    price: Decimal = Field(gt=0, lt=1)
    size: Decimal = Field(gt=0)


class Book(Model):
    asset_id: str
    observed_at: datetime
    bids: list[Level]
    asks: list[Level]
    minimum: Decimal = Field(gt=0)
    tick: Decimal = Field(gt=0, lt=1)
    fee_rate: Decimal = Field(ge=0, le=1)
    fee_exponent: Decimal = Field(default=D("1"), ge=0)
    evidence: str


class Market(Model):
    id: str
    slug: str
    url: str = ""
    question: str
    description: str
    resolution_source: str = ""
    condition_id: str | None = None
    version: str
    group: str
    category: str = "Unclassified"
    end_at: datetime | None = None
    active: bool
    resolved: bool = False
    payouts: dict[str, Decimal] = Field(default_factory=dict)
    liquidity: Decimal = ZERO
    volume: Decimal = ZERO
    assets: dict[str, str]
    books: dict[str, Book] = Field(default_factory=dict)
    history: dict[str, list[dict]] = Field(default_factory=dict)


class Decision(Model):
    agent_id: str
    market_id: str
    outcome: Literal["YES", "NO"] | None
    action: Literal["BUY", "SELL", "HOLD", "WAIT"]
    estimated_probability: Decimal = Field(ge=0, le=1)
    confidence: Decimal = Field(ge=0, le=1)
    reasoning: str = Field(max_length=6000)
    sources: list[str] = Field(max_length=12)
    proposed_stake: Decimal = Field(ge=0)
    expected_edge: Decimal
    exit_plan: str = Field(max_length=2000)
    risk_factors: list[str]
    decision_kind: Literal["STRATEGIC", "EXPLORATION"] = "STRATEGIC"
    probability_basis: Literal["ESTIMATED", "UNESTIMATED"] = "ESTIMATED"

    @model_validator(mode="after")
    def trade_outcome(self):
        if self.action in ("BUY", "SELL") and not self.outcome:
            raise ValueError("A trade needs an outcome")
        if self.probability_basis == "UNESTIMATED":
            if self.estimated_probability != Decimal("0.5") or self.confidence != 0 or self.expected_edge != 0:
                raise ValueError("Unestimated probability must use the neutral placeholder and zero confidence")
            if self.action == "BUY" and self.decision_kind != "EXPLORATION":
                raise ValueError("Unestimated BUY is only permitted as disclosed exploration")
        if self.decision_kind == "EXPLORATION" and self.action != "BUY":
            raise ValueError("Exploration is a participation BUY")
        return self


class Fill(Model):
    price: Decimal
    quantity: Decimal
    fee: Decimal


class Execution(Model):
    status: Literal["FILLED", "PARTIAL", "REJECTED"]
    fills: list[Fill] = Field(default_factory=list)
    reason: str = ""

    @property
    def quantity(self):
        return sum((f.quantity for f in self.fills), ZERO)

    @property
    def gross(self):
        return sum((f.price * f.quantity for f in self.fills), ZERO)

    @property
    def fees(self):
        return sum((f.fee for f in self.fills), ZERO)


class Position(Model):
    market_id: str
    outcome: Literal["YES", "NO"]
    quantity: Decimal = ZERO
    cost: Decimal = ZERO


class Wallet(Model):
    initial: Decimal = Field(gt=0)
    cash: Decimal = Field(ge=0)
    realized: Decimal = ZERO
    positions: dict[str, Position] = Field(default_factory=dict)


def position_key(market_id, outcome):
    return f"{market_id}:{outcome}"
