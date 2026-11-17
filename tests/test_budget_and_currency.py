import pytest

from snackcounter.money import Money, RateTable
from snackcounter.refill_service import BudgetExceeded
from snackcounter.reporting import monthly_report
from conftest import OSLO, BLR

MONTH = (2026, 11)


def test_commit_refused_when_typical_purchase_would_exceed_budget(world):
    # 4 purchases of 1200 = 4800; remaining 1200 -> exactly one more fits; then none
    for i in range(4):
        r = world.svc.report_empty(OSLO)
        world.buy(r, r.offered_to[0], 1200, "NOK")
    r = world.svc.report_empty(OSLO)
    v = r.offered_to[0]
    world.svc.commit(r.id, v)                              # 4800 + 1200 reserved = 6000 OK
    assert world.svc.budget.remaining(OSLO, MONTH).minor == 0
    world.svc.complete_purchase(r.id, v, Money.of(1200, "NOK"), {"nuts": 1}, "r.jpg")
    r2 = world.svc.report_empty(OSLO)
    with pytest.raises(BudgetExceeded):
        world.svc.commit(r2.id, r2.offered_to[0])
    world.svc.commit(r2.id, r2.offered_to[0], override_budget=True)   # manager approval


def test_reservations_stop_parallel_commitments_blowing_budget(world):
    # Oslo budget 6000: spent 3600 -> room for exactly one 1200 reservation + one more (2400 left)
    for _ in range(3):
        r = world.svc.report_empty(OSLO)
        world.buy(r, r.offered_to[0], 1200, "NOK")
    assert world.svc.budget.can_commit(OSLO, MONTH)
    r = world.svc.report_empty(OSLO)
    world.svc.commit(r.id, r.offered_to[0])
    assert world.svc.budget.remaining(OSLO, MONTH) == Money.of(1200, "NOK")


def test_budgets_are_per_office_and_currency(world):
    r = world.svc.report_empty(BLR)
    world.buy(r, r.offered_to[0], 14000, "INR")
    assert world.svc.budget.remaining(BLR, MONTH) == Money.of(1000, "INR")
    assert world.svc.budget.remaining(OSLO, MONTH) == Money.of(6000, "NOK")   # untouched
    r2 = world.svc.report_empty(BLR)
    with pytest.raises(BudgetExceeded):                    # 1000 left < 3000 typical max
        world.svc.commit(r2.id, r2.offered_to[0])


def test_purchase_must_be_in_office_currency(world):
    r = world.svc.report_empty(OSLO)
    v = r.offered_to[0]
    world.svc.commit(r.id, v)
    with pytest.raises(ValueError):
        world.svc.complete_purchase(r.id, v, Money.of(500, "INR"), {}, "r.jpg")


def test_monthly_report_totals_across_both_currencies(world):
    r = world.svc.report_empty(OSLO)
    world.buy(r, r.offered_to[0], 1000, "NOK", {"chips": 2})
    r = world.svc.report_empty(BLR)
    world.buy(r, r.offered_to[0], 2000, "INR", {"chips": 5, "fruit": 4})
    rep = monthly_report(world.svc.budget, world.rates, MONTH, world.svc.items_by_office(MONTH))
    assert rep["offices"][OSLO]["spent"] == Money.of(1000, "NOK")
    assert rep["offices"][BLR]["spent"] == Money.of(2000, "INR")
    assert rep["offices"][BLR]["remaining"] == Money.of(13000, "INR")
    assert rep["total"] == Money.of(1250, "NOK")           # 1000 + 2000 * 0.125
    assert rep["offices"][BLR]["items"] == {"chips": 5, "fruit": 4}


def test_report_converts_once_so_rounding_does_not_accumulate(world):
    rates = RateTable("NOK", {"INR": "0.1234"})
    for _ in range(3):
        r = world.svc.report_empty(BLR)
        world.buy(r, r.offered_to[0], 500.01, "INR")
    rep = monthly_report(world.svc.budget, rates, MONTH)
    assert rep["offices"][BLR]["spent"] == Money.of(1500.03, "INR")
    assert rep["total"] == rates.convert(Money.of(1500.03, "INR"), "NOK")


def test_money_is_exact_and_rejects_mixed_currency():
    assert Money.of("0.1", "NOK") + Money.of("0.2", "NOK") == Money.of("0.3", "NOK")
    with pytest.raises(ValueError):
        Money.of(1, "NOK") + Money.of(1, "INR")


def test_purchase_above_typical_max_is_recorded_and_warns_managers(world):
    r = world.svc.report_empty(BLR)
    done = world.buy(r, r.offered_to[0], 5000, "INR")      # reserved 3000, actually spent 5000
    assert done.state.value == "CLAIM_SUBMITTED"            # never blocked: money already spent
    assert world.svc.budget.spent(BLR, MONTH) == Money.of(5000, "INR")
    msgs = world.chat.of_kind("over_budget")
    assert len(msgs) == 1 and msgs[0].to == "managers:Bengaluru"
    assert "typical maximum" in done.over_budget_warning


def test_purchase_pushing_month_over_budget_warns_managers(world):
    for _ in range(4):
        r = world.svc.report_empty(BLR)
        world.buy(r, r.offered_to[0], 3000, "INR")          # 12000 spent
    r = world.svc.report_empty(BLR)
    world.svc.commit(r.id, r.offered_to[0])                  # 12000 + 3000 reserved = 15000 fits
    world.svc.complete_purchase(r.id, r.assignee, Money.of(3000, "INR"), {}, "r.jpg")
    assert not world.chat.of_kind("over_budget")            # exactly on budget: no warning
    r = world.svc.report_empty(BLR)
    world.svc.commit(r.id, r.offered_to[0], override_budget=True)
    world.svc.complete_purchase(r.id, r.assignee, Money.of(500, "INR"), {}, "r.jpg")
    assert "exceeds budget" in r.over_budget_warning


def test_normal_purchase_does_not_warn(world):
    r = world.svc.report_empty(OSLO)
    world.buy(r, r.offered_to[0], 800, "NOK")
    assert not world.chat.of_kind("over_budget") and r.over_budget_warning == ""
