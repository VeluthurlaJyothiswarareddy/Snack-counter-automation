# Snack Counter Automation

Automates the snack-refill process for the Oslo and Bengaluru offices: from "box is empty" to
"volunteer reimbursed", with fair volunteer selection, budget control in two currencies, and one
monthly report.

Humans still do the shopping. The system removes the coordination work: it creates one owned task per
empty box, picks a fair volunteer, chases and reassigns if nobody acts, files the HR claim for them,
and enforces budgets.

> Design rationale, trade-offs and what was deliberately not built: see **[DESIGN.md](DESIGN.md)**.

## Quick start

Requires Python 3.10+ and `pytest`. There are no other dependencies.

```bash
python3 -m pytest -q        # run all tests (30)
python3 -m pytest -v        # list each test
```

## Refill lifecycle

```
OFFERED -> COMMITTED -> PURCHASED -> CLAIM_SUBMITTED -> REIMBURSED
   |           |                           \-> CLAIM_REJECTED
   |           \- deadline missed -> released -> re-offered to someone else
   \- nobody accepts / nobody eligible -> ESCALATED (managers notified, retried)
```

1. Someone reports "box is empty". At most **one active refill per office**.
2. A small batch of eligible volunteers is offered the task. Offers expire after 2h.
3. The first "I'll take it" wins (atomic). The budget is checked and a typical-max amount reserved. A 24h deadline starts.
4. The volunteer submits amount, items and receipt. Spend is booked and the HR claim is created automatically.
5. HR is polled: approved means `REIMBURSED`, rejected alerts managers.

## Project layout

```
.
├── DESIGN.md                       design document
├── pyproject.toml                  pytest configuration
├── src/snackcounter/
│   ├── money.py                    Money (integer minor units), RateTable for currency conversion
│   ├── models.py                   Office, Volunteer, Refill, State, Config
│   ├── clock.py                    SystemClock / FakeClock (testable timeouts)
│   ├── selection.py                who buys: eligibility + fairness ranking (pure function)
│   ├── budget.py                   per-office/month ledger, reservations, budget check
│   ├── refill_service.py           lifecycle: commit, decline, purchase, tick (timers, retries)
│   ├── reporting.py                monthly report across both currencies
│   └── adapters/
│       ├── chat.py                 FakeChat: simulated internal chat tool
│       └── hr.py                   FakeHR: simulated HR system
└── tests/
    ├── conftest.py                 shared test world (offices, volunteers, fakes)
    ├── test_no_double_commit.py
    ├── test_timeout_reassign.py
    ├── test_budget_and_currency.py
    ├── test_selection_fairness.py
    └── test_hr_and_payroll.py
```

## Key rules and where they are tested

| Rule | Test file |
|---|---|
| Two people cannot commit to the same refill (including 20 racing threads) | `test_no_double_commit.py` |
| Duplicate "empty" reports create one refill | `test_no_double_commit.py` |
| A refill nobody completes is handed to someone else; failed volunteer cannot grab it back | `test_timeout_reassign.py` |
| Unanswered offers move on; no takers escalates to managers | `test_timeout_reassign.py` |
| Budgets are per office and currency; parallel commitments cannot overspend | `test_budget_and_currency.py` |
| Monthly totals are correct across NOK and INR (1000 NOK + 2000 INR = 1250 NOK) | `test_budget_and_currency.py` |
| Over-budget purchases are recorded and managers warned | `test_budget_and_currency.py` |
| Fair selection, holiday, visitors, cap on unreimbursed money | `test_selection_fairness.py` |
| Full path to reimbursed, HR outage retry without duplicate claims, payroll currency, rejection | `test_hr_and_payroll.py` |

## Try it by hand

```bash
python3 -I - <<'EOF'
import sys; sys.path[:0] = ["src", "tests"]
from conftest import World, OSLO
from snackcounter.money import Money

w = World()
r = w.svc.report_empty(OSLO);        print(r.state, r.offered_to)
w.svc.commit(r.id, r.offered_to[0]); print(r.state, r.assignee)
w.svc.complete_purchase(r.id, r.assignee, Money.of(800, "NOK"), {"chips": 3}, "r.jpg")
print(r.state, r.claim_id)
w.hr.approve(r.claim_id); w.svc.tick(); print(r.state)
print(*r.history, sep="\n")          # readable audit trail
EOF
```

## Configuration

Defaults live in `Config` (`models.py`): batch size 2, offer expiry 2h, purchase deadline 24h,
fairness window 90 days, and a cap on how much a volunteer may be out of pocket (3 000 NOK equivalent).
Offices, budgets and typical maximum purchases are defined as `Office` objects; exchange rates in `RateTable`.

## Assumptions

- A person reports the box as empty (no sensor).
- HR converts currency to the employee's payroll currency and exposes claim status by polling.
- Budget is counted by purchase date.
- Availability is self-declared (`away_until`), with no calendar integration.
- Exchange rates are fixed placeholders (1 INR = 0.125 NOK), not a live feed.

## Limitations

State is in memory; the lock in `RefillService` stands in for a database transaction. Chat and HR are
simulated. There are no pre-deadline reminders, no receipt OCR and no UI beyond chat. See
[DESIGN.md](DESIGN.md) for the full list and reasoning.
# Snack-counter-automation
