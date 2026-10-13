from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, AwareDatetime

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
    features: dict = Field(default_factory=dict)
    category_source: str = "unknown"
    resolved_at: datetime | None = None
    seconds_delay: int = 0


class LearningReview(Model):
    episode_ids: list[str] = Field(min_length=1, max_length=8)
    lesson: str = Field(min_length=1, max_length=700)
    adaptation: str = Field(min_length=1, max_length=700)


class ExitRules(Model):
    stop_bid: Decimal | None = Field(default=None, gt=0, lt=1)
    take_profit_bid: Decimal | None = Field(default=None, gt=0, lt=1)
    exit_at: AwareDatetime | None = None


class EvidenceClaim(Model):
    url: str = Field(max_length=600)
    quote: str = Field(min_length=15, max_length=400)
    claim: str = Field(max_length=600)


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
    learning_review: list[LearningReview] = Field(default_factory=list, max_length=3)
    thesis_type: Literal["RESOLUTION", "PRICE_MOVE"] = "RESOLUTION"
    target_price: Decimal | None = Field(default=None, gt=0, lt=1)
    horizon_hours: int | None = Field(default=None, ge=1, le=168)
    max_buy_price: Decimal | None = Field(default=None, gt=0, lt=1)
    min_sell_price: Decimal | None = Field(default=None, gt=0, lt=1)
    sell_quantity: Decimal | None = Field(default=None, gt=0)
    close_position: bool = False
    exit_rules: ExitRules | None = None
    claims: list[EvidenceClaim] = Field(default_factory=list, max_length=4)
    applied_lesson_ids: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def trade_outcome(self):
        if self.action in ("BUY", "SELL") and not self.outcome:
            raise ValueError("A trade needs an outcome")
        if self.probability_basis == "UNESTIMATED":
            if (
                self.estimated_probability != Decimal("0.5")
                or self.confidence != 0
                or self.expected_edge != 0
            ):
                raise ValueError(
                    "Unestimated probability must use the neutral placeholder and zero confidence"
                )
            if (
                self.action == "BUY"
                and self.decision_kind != "EXPLORATION"
                and self.thesis_type != "PRICE_MOVE"
            ):
                raise ValueError(
                    "Unestimated BUY is only permitted as disclosed exploration"
                )
        if (
            self.action == "BUY"
            and self.thesis_type == "PRICE_MOVE"
            and (
                self.target_price is None
                or self.horizon_hours is None
                or self.max_buy_price is None
            )
        ):
            raise ValueError(
                "Price-move BUY needs target_price, horizon_hours and max_buy_price"
            )
        if self.decision_kind == "EXPLORATION" and self.action != "BUY":
            raise ValueError("Exploration is a participation BUY")
        return self


class DecisionPlan(Model):
    agent_id: str
    actions: list[Decision] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def identity(self):
        if any(a.agent_id != self.agent_id for a in self.actions):
            raise ValueError("Plan actions must belong to the same agent")
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
    exit_rules: ExitRules | None = None
    exit_plan: str = ""


class Wallet(Model):
    initial: Decimal = Field(gt=0)
    cash: Decimal = Field(ge=0)
    realized: Decimal = ZERO
    positions: dict[str, Position] = Field(default_factory=dict)


def position_key(market_id, outcome):
    return f"{market_id}:{outcome}"
