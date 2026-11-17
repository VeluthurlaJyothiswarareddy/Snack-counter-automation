"""Simulated HR system (run by another company).

Contract we rely on: create a claim (amount, currency, description, receipt, employee id);
approval is asynchronous (1-10 days); employee is paid in their PAYROLL currency.
We assume HR does the currency conversion; we only send the receipt amount/currency.
"""
from dataclasses import dataclass

from ..money import Money, RateTable


class HRUnavailable(Exception):
    pass


@dataclass
class Claim:
    id: str
    employee_id: str
    amount: Money
    description: str
    receipt: str
    status: str = "PENDING"           # PENDING | APPROVED | REJECTED
    paid: Money | None = None         # amount paid out in payroll currency


class FakeHR:
    def __init__(self, payroll_currency_of: dict[str, str], rates: RateTable):
        self._payroll = payroll_currency_of
        self._rates = rates
        self.claims: dict[str, Claim] = {}
        self._by_key: dict[str, str] = {}
        self.down = False

    def create_claim(self, employee_id: str, amount: Money, description: str,
                     receipt: str, idempotency_key: str) -> str:
        if self.down:
            raise HRUnavailable()
        if idempotency_key in self._by_key:        # retries never create duplicates
            return self._by_key[idempotency_key]
        cid = f"CLM-{len(self.claims) + 1}"
        self.claims[cid] = Claim(cid, employee_id, amount, description, receipt)
        self._by_key[idempotency_key] = cid
        return cid

    def get_status(self, claim_id: str) -> str:
        if self.down:
            raise HRUnavailable()
        return self.claims[claim_id].status

    # test / simulation controls (HR's side of the world)
    def approve(self, claim_id: str) -> None:
        c = self.claims[claim_id]
        c.status = "APPROVED"
        c.paid = self._rates.convert(c.amount, self._payroll[c.employee_id])

    def reject(self, claim_id: str) -> None:
        self.claims[claim_id].status = "REJECTED"
