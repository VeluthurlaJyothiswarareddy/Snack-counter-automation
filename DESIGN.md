# Snack Counter Automation: Design

## What "automate" means here
Remove the *coordination* work, not the shopping. The system (1) turns "box is empty" into exactly one
owned task, (2) picks a fair volunteer, (3) chases and reassigns if nobody acts, (4) files the HR claim for
them, (5) enforces budgets and reports. It lives in the chat tool (buttons/DMs, company login), so there
is nothing new to install. Humans still buy: a robot can't carry snacks.

## Lifecycle: empty to reimbursed
`OFFERED -> COMMITTED -> PURCHASED -> CLAIM_SUBMITTED -> REIMBURSED` (also `ESCALATED`, `CLAIM_REJECTED`)
1. Anyone taps **"Box is empty"** in chat. Idempotent: at most **one active refill per office**.
2. Selector offers it to a small batch (2) of eligible volunteers. Offer expires after 2h, so the next batch is asked.
3. First **"I'll take it"** wins (atomic). Budget is checked and a typical-max amount reserved. Others get "taken". 24h deadline starts.
4. Volunteer uploads receipt + amount + items in chat. Spend is booked, and the system **creates the HR claim for them** (idempotency key `refill-<id>`; retried if HR is down).
5. System polls HR: approved -> `REIMBURSED` (volunteer notified); rejected -> managers alerted.
6. Deadline missed -> volunteer excluded, reservation released, refill re-offered. Nobody eligible or everyone passed -> `ESCALATED` (managers pinged, everyone retried next tick).

## Parts and the data each keeps
| Part | Data |
|---|---|
| Refill service (lifecycle, one lock/transaction) | refill: office, state, offered_to, excluded, assignee, deadline, amount, items, receipt, claim id, audit history |
| Selector (pure function) | volunteer: home/current office, payroll currency, away_until; derived: refills in last 90d, unreimbursed exposure, last refill date |
| Budget ledger | per office/month spend in *office currency*; open reservations |
| Reporting | derived from ledger and items: native totals, remaining, items bought, combined total in NOK |
| Chat adapter / HR adapter | interfaces; simulated by `FakeChat` / `FakeHR` |

## How each problem is prevented
- **Empty for days / "someone else will"**: explicit owner, 2h offer and 24h purchase timers, automatic reassign, escalation to managers.
- **Two people buy same day**: one active refill per office, atomic commit (tested with 20 racing threads).
- **A few people do everything, slow payback**: rank by fewest recent refills, then lowest unreimbursed exposure; people over an exposure cap (3 000 NOK-equiv.) are skipped; claim is filed automatically so the 1-10 day HR wait starts at purchase.
- **No visibility**: every purchase is structured (amount, currency, items); one monthly report. Items bought is a *proxy* for what is eaten.
- **Hybrid / holiday / visitors**: eligibility uses `current_office` and `away_until`, not the home office. Non-response is handled by timers rather than by assuming presence.

## Money and currency decisions
- Integer minor units (`Money`), never floats; mixing currencies raises.
- Each office budgets in its own currency (NOK / INR). Commit requires `spent + reserved + typical_max <= budget`. Reserving the typical maximum stops parallel commitments jointly overspending. Over budget needs an explicit manager override (not a silent block, not a silent pass). If a receipt is larger than the reserved typical max, or pushes the month over budget, the spend is still recorded (money is already gone) but managers are warned.
- Purchases are in the office's currency (that's where the shop is). The claim carries the receipt amount and currency; **HR pays in the employee's payroll currency** (a visiting Oslo employee buying in INR is paid in NOK). We assume HR converts.
- Report: exact native totals per office, plus one combined NOK total converted once per currency with a stated, configurable rate table.

## Assumptions (would confirm with stakeholders)
Empty is reported by a person; HR converts currency and exposes claim status by polling; budget is by purchase date; chat provides button callbacks; calendar integration unavailable, so availability is self-declared `away_until`.

## Trade-offs and what I would deliberately NOT build
- Not built: receipt OCR (the volunteer types the amount), sensors / weight-based empty detection, live FX feed (fixed rates), real chat/HR integrations, any UI beyond chat, automatic purchasing, per-snack consumption analytics, working-hours-aware timers, a persistent database (in-memory state; the lock stands in for a DB transaction).
- Batch offers (2) trade a little duplicated notification for speed; sequential offers would be slower when people are away.
- Reserving *typical max* is conservative: it can block a commit when only a cheap purchase would have fit. Chosen because overspend is worse and an override exists.
- Fairness is a heuristic (counts + exposure), not an optimizer. Easy to explain, easy to change in one function.
- Reminders before the deadline are not built; a mid-deadline nudge is the first thing I'd add.
