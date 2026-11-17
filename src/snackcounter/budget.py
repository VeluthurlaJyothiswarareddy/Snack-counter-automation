"""Budget ledger: spend per office/month in the office's own currency, plus reservations.

Check at commit time:  spent_this_month + reserved_by_open_commitments + typical_max <= budget.
Reserving the *typical maximum* (not the unknown actual) keeps two parallel commitments
from jointly blowing the budget.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import Office
from .money import Money


@dataclass(frozen=True)
class Spend:
    office: str
    refill_id: int
    amount: Money
    month: tuple[int, int]


def month_key(dt: datetime) -> tuple[int, int]:
    return (dt.year, dt.month)


class BudgetLedger:
    def __init__(self, offices: dict[str, Office]):
        self.offices = offices
        self.spends: list[Spend] = []
        self._reservations: dict[int, tuple[str, Money]] = {}

    def spent(self, office: str, month: tuple[int, int]) -> Money:
        total = Money.zero(self.offices[office].currency)
        for s in self.spends:
            if s.office == office and s.month == month:
                total = total + s.amount
        return total

    def reserved(self, office: str) -> Money:
        total = Money.zero(self.offices[office].currency)
        for off, amt in self._reservations.values():
            if off == office:
                total = total + amt
        return total

    def remaining(self, office: str, month: tuple[int, int]) -> Money:
        o = self.offices[office]
        return o.monthly_budget - self.spent(office, month) - self.reserved(office)

    def can_commit(self, office: str, month: tuple[int, int]) -> bool:
        return self.offices[office].typical_max <= self.remaining(office, month)

    def reserve(self, refill_id: int, office: str) -> None:
        self._reservations[refill_id] = (office, self.offices[office].typical_max)

    def release(self, refill_id: int) -> None:
        self._reservations.pop(refill_id, None)

    def record_spend(self, refill_id: int, office: str, amount: Money, when: datetime) -> None:
        if amount.currency != self.offices[office].currency:
            raise ValueError(f"{office} purchases must be in {self.offices[office].currency}")
        self.release(refill_id)
        self.spends.append(Spend(office, refill_id, amount, month_key(when)))
