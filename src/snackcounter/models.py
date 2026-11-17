from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from .money import Money


class State(str, Enum):
    OFFERED = "OFFERED"              # box reported empty, offered to a batch of volunteers
    COMMITTED = "COMMITTED"          # exactly one volunteer owns it, with a deadline
    ESCALATED = "ESCALATED"          # nobody eligible / nobody accepted: humans notified
    PURCHASED = "PURCHASED"          # box refilled, spend booked, claim not yet accepted by HR
    CLAIM_SUBMITTED = "CLAIM_SUBMITTED"
    REIMBURSED = "REIMBURSED"        # terminal
    CLAIM_REJECTED = "CLAIM_REJECTED"  # terminal, needs human follow-up


# While a refill is in one of these states the box still needs filling.
ACTIVE = {State.OFFERED, State.COMMITTED, State.ESCALATED}
# States where the volunteer is out of pocket (counts towards their exposure).
OUT_OF_POCKET = {State.PURCHASED, State.CLAIM_SUBMITTED}


@dataclass(frozen=True)
class Office:
    name: str
    currency: str
    monthly_budget: Money
    typical_max: Money   # reserved against the budget when someone commits


@dataclass
class Volunteer:
    id: str
    name: str
    home_office: str
    current_office: str          # differs from home_office while visiting
    payroll_currency: str
    away_until: datetime | None = None   # holiday / out of office


@dataclass
class Refill:
    id: int
    office: str
    created_at: datetime
    state: State = State.OFFERED
    offered_to: list[str] = field(default_factory=list)
    excluded: set[str] = field(default_factory=set)   # declined / timed out
    offer_expires_at: datetime | None = None
    assignee: str | None = None
    deadline: datetime | None = None
    amount: Money | None = None
    items: dict[str, int] = field(default_factory=dict)   # snack -> quantity
    purchased_at: datetime | None = None
    receipt: str = ""
    claim_id: str | None = None
    escalation_notified: bool = False
    over_budget_warning: str = ""   # set when the purchase pushed the office over budget
    history: list[str] = field(default_factory=list)       # audit trail


@dataclass(frozen=True)
class Config:
    batch_size: int = 2                       # volunteers offered at once
    offer_ttl: timedelta = timedelta(hours=2)
    purchase_deadline: timedelta = timedelta(hours=24)
    fairness_window: timedelta = timedelta(days=90)
    # max money a volunteer may be out of pocket (NOK-equivalent minor units, see service)
    exposure_cap: Money = Money(300_000, "NOK")
