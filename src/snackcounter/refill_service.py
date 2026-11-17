"""Refill lifecycle: EMPTY -> OFFERED -> COMMITTED -> PURCHASED -> CLAIM_SUBMITTED -> REIMBURSED.

All state changes happen under one lock, so "two people commit to the same refill" is
impossible (first caller wins, the rest get AlreadyTaken). In production the lock becomes
a DB transaction / conditional UPDATE ... WHERE state='OFFERED'.
"""
from __future__ import annotations

import threading
from datetime import datetime

from .adapters.chat import FakeChat
from .adapters.hr import HRUnavailable
from .budget import BudgetLedger, month_key
from .models import ACTIVE, OUT_OF_POCKET, Config, Office, Refill, State, Volunteer
from .money import Money, RateTable
from .selection import rank_candidates


class RefillError(Exception):
    pass


class AlreadyTaken(RefillError):
    pass


class NotOffered(RefillError):
    pass


class InvalidState(RefillError):
    pass


class BudgetExceeded(RefillError):
    pass


class RefillService:
    def __init__(self, offices: dict[str, Office], volunteers: list[Volunteer], chat: FakeChat,
                 hr, clock, rates: RateTable, config: Config = Config()):
        self.offices = offices
        self.volunteers = {v.id: v for v in volunteers}
        self.chat, self.hr, self.clock, self.rates, self.cfg = chat, hr, clock, rates, config
        self.budget = BudgetLedger(offices)
        self.refills: dict[int, Refill] = {}
        self._lock = threading.RLock()
        self._next_id = 1

    # ---------- public API (what chat buttons / HR polling would call) ----------

    def report_empty(self, office: str) -> Refill:
        """Someone taps 'box is empty'. Idempotent: one active refill per office."""
        with self._lock:
            for r in self.refills.values():
                if r.office == office and r.state in ACTIVE:
                    return r          # prevents duplicate refills / duplicate buying
            r = Refill(self._next_id, office, self.clock.now())
            self._next_id += 1
            self.refills[r.id] = r
            self._log(r, "reported empty")
            self._offer(r)
            return r

    def commit(self, refill_id: int, volunteer_id: str, override_budget: bool = False) -> Refill:
        with self._lock:
            r = self._get(refill_id)
            if r.state == State.COMMITTED or r.state not in ACTIVE:
                raise AlreadyTaken(f"refill {r.id} already {r.state.value} (by {r.assignee})")
            if r.state != State.OFFERED or volunteer_id not in r.offered_to:
                raise NotOffered(f"{volunteer_id} was not offered refill {r.id}")
            now = self.clock.now()
            if not override_budget and not self.budget.can_commit(r.office, month_key(now)):
                raise BudgetExceeded(
                    f"{r.office}: remaining {self.budget.remaining(r.office, month_key(now))}"
                    " is below a typical purchase; manager approval needed")
            self.budget.reserve(r.id, r.office)
            r.state, r.assignee = State.COMMITTED, volunteer_id
            r.deadline = now + self.cfg.purchase_deadline
            for other in r.offered_to:
                if other != volunteer_id:
                    self.chat.send(other, "taken", r.id, "Someone else took this refill")
            self._log(r, f"committed by {volunteer_id}")
            return r

    def decline(self, refill_id: int, volunteer_id: str) -> Refill:
        with self._lock:
            r = self._get(refill_id)
            if r.state != State.OFFERED or volunteer_id not in r.offered_to:
                raise NotOffered(f"{volunteer_id} was not offered refill {r.id}")
            r.excluded.add(volunteer_id)
            r.offered_to.remove(volunteer_id)
            self._log(r, f"declined by {volunteer_id}")
            if not r.offered_to:
                self._offer(r)
            return r

    def complete_purchase(self, refill_id: int, volunteer_id: str, amount: Money,
                          items: dict[str, int], receipt: str) -> Refill:
        with self._lock:
            r = self._get(refill_id)
            if r.state != State.COMMITTED or r.assignee != volunteer_id:
                raise InvalidState(f"refill {r.id} is not committed to {volunteer_id}")
            now = self.clock.now()
            self.budget.record_spend(r.id, r.office, amount, now)   # also drops the reservation
            r.state, r.amount, r.items, r.purchased_at = State.PURCHASED, amount, items, now
            r.receipt = receipt
            self._log(r, f"purchased {amount}")
            self._warn_if_over_budget(r)
            self._submit_claim(r)
            return r

    def tick(self) -> None:
        """Called periodically (every few minutes). Handles every time-based rule."""
        with self._lock:
            now = self.clock.now()
            for r in list(self.refills.values()):
                if r.state == State.OFFERED and r.offer_expires_at and now >= r.offer_expires_at:
                    r.excluded.update(r.offered_to)       # didn't react: try someone else
                    self._log(r, "offer expired")
                    self._offer(r)
                elif r.state == State.COMMITTED and r.deadline and now >= r.deadline:
                    self._release(r)
                elif r.state == State.ESCALATED:
                    r.excluded.clear()                    # everyone gets another chance
                    self._offer(r)
                elif r.state == State.PURCHASED:
                    self._submit_claim(r)                 # retry after HR outage
                elif r.state == State.CLAIM_SUBMITTED:
                    self._sync_claim(r)

    # ---------- queries ----------

    def exposure(self, volunteer_id: str) -> Money:
        """Money the volunteer is out of pocket for, in the reporting (base) currency."""
        total = Money.zero(self.rates.base)
        for r in self.refills.values():
            if r.assignee == volunteer_id and r.state in OUT_OF_POCKET and r.amount:
                total = total + self.rates.convert(r.amount, self.rates.base)
        return total

    def items_by_office(self, month: tuple[int, int]) -> dict[str, dict[str, int]]:
        """Which snacks were bought (proxy for 'what gets eaten'), per office."""
        out: dict[str, dict[str, int]] = {}
        for r in self.refills.values():
            if r.purchased_at and month_key(r.purchased_at) == month:
                bucket = out.setdefault(r.office, {})
                for name, qty in r.items.items():
                    bucket[name] = bucket.get(name, 0) + qty
        return out

    # ---------- internals ----------

    def _get(self, refill_id: int) -> Refill:
        return self.refills[refill_id]

    def _log(self, r: Refill, msg: str) -> None:
        r.history.append(f"{self.clock.now().isoformat()} {msg}")

    def _offer(self, r: Refill) -> None:
        now = self.clock.now()
        window_start = now - self.cfg.fairness_window
        counts: dict[str, int] = {}
        last: dict[str, datetime] = {}
        for o in self.refills.values():
            if o.assignee and o.purchased_at:
                last[o.assignee] = max(last.get(o.assignee, o.purchased_at), o.purchased_at)
                if o.purchased_at >= window_start:
                    counts[o.assignee] = counts.get(o.assignee, 0) + 1
        exposure = {v: self.exposure(v).minor for v in self.volunteers}
        ranked = rank_candidates(r, list(self.volunteers.values()), now, counts, exposure, last,
                                 self.rates.convert(self.cfg.exposure_cap, self.rates.base).minor)
        batch = ranked[: self.cfg.batch_size]
        if not batch:
            r.state, r.offered_to, r.offer_expires_at = State.ESCALATED, [], None
            if not r.escalation_notified:
                r.escalation_notified = True
                self.chat.send(f"managers:{r.office}", "escalation", r.id,
                               "Snack box empty and no volunteer is available")
            self._log(r, "escalated: no eligible volunteer")
            return
        r.state, r.offered_to = State.OFFERED, [v.id for v in batch]
        r.offer_expires_at = now + self.cfg.offer_ttl
        for v in batch:
            self.chat.send(v.id, "offer", r.id, "Snack box is empty. Can you refill it?")
        self._log(r, f"offered to {r.offered_to}")

    def _warn_if_over_budget(self, r: Refill) -> None:
        """The money is already spent, so never block: record it, flag it, tell managers."""
        office = self.offices[r.office]
        month = month_key(r.purchased_at)
        reasons = []
        if office.typical_max < r.amount:
            reasons.append(f"purchase {r.amount} exceeds typical maximum {office.typical_max}")
        spent = self.budget.spent(r.office, month)
        if office.monthly_budget < spent:
            reasons.append(f"month spend {spent} exceeds budget {office.monthly_budget}")
        if reasons:
            r.over_budget_warning = "; ".join(reasons)
            self.chat.send(f"managers:{r.office}", "over_budget", r.id, r.over_budget_warning)
            self._log(r, f"WARNING {r.over_budget_warning}")

    def _release(self, r: Refill) -> None:
        """Committed volunteer missed the deadline: free the slot and hand it on."""
        failed = r.assignee
        self.budget.release(r.id)
        self.chat.send(failed, "reassigned", r.id, "Refill was handed to someone else")
        r.excluded.add(failed)
        r.assignee = r.deadline = None
        self._log(r, f"{failed} missed deadline; released")
        self._offer(r)

    def _submit_claim(self, r: Refill) -> None:
        try:
            r.claim_id = self.hr.create_claim(
                employee_id=r.assignee, amount=r.amount,
                description=f"Snack refill {r.office} #{r.id}",
                receipt=r.receipt,
                idempotency_key=f"refill-{r.id}")        # same key on every retry
            r.state = State.CLAIM_SUBMITTED
            self._log(r, f"claim {r.claim_id} submitted")
        except HRUnavailable:
            self._log(r, "HR unavailable; will retry")

    def _sync_claim(self, r: Refill) -> None:
        try:
            status = self.hr.get_status(r.claim_id)
        except HRUnavailable:
            return
        if status == "APPROVED":
            r.state = State.REIMBURSED
            self.chat.send(r.assignee, "reimbursed", r.id, "Your claim was paid")
            self._log(r, "reimbursed")
        elif status == "REJECTED":
            r.state = State.CLAIM_REJECTED
            self.chat.send(f"managers:{r.office}", "rejected", r.id, "HR rejected the claim")
            self._log(r, "claim rejected")
