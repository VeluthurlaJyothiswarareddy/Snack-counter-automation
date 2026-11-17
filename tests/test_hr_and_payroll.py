from snackcounter.models import State
from snackcounter.money import Money
from snackcounter.models import Config
from conftest import OSLO, BLR, World


def test_happy_path_empty_to_reimbursed(world):
    r = world.svc.report_empty(OSLO)
    v = r.offered_to[0]
    world.buy(r, v, 800, "NOK")
    assert r.state == State.CLAIM_SUBMITTED
    claim = world.hr.claims[r.claim_id]
    assert (claim.employee_id, claim.amount) == (v, Money.of(800, "NOK"))
    world.svc.tick()
    assert r.state == State.CLAIM_SUBMITTED          # HR hasn't decided yet
    world.hr.approve(r.claim_id)
    world.svc.tick()
    assert r.state == State.REIMBURSED
    assert world.svc.exposure(v).minor == 0          # no longer out of pocket
    assert world.chat.of_kind("reimbursed")


def test_hr_outage_retries_without_duplicate_claims(world):
    world.hr.down = True
    r = world.svc.report_empty(OSLO)
    world.buy(r, r.offered_to[0], 400, "NOK")
    assert r.state == State.PURCHASED and not world.hr.claims
    world.svc.tick()                                 # still down
    world.hr.down = False
    world.svc.tick(); world.svc.tick()
    assert r.state == State.CLAIM_SUBMITTED and len(world.hr.claims) == 1


def test_visitor_paid_in_payroll_currency():
    w = World(Config(batch_size=20))
    w.volunteer("o1").current_office = BLR           # Oslo employee visiting Bengaluru
    r = w.svc.report_empty(BLR)
    assert "o1" in r.offered_to
    w.svc.commit(r.id, "o1")
    w.svc.complete_purchase(r.id, "o1", Money.of(2000, "INR"), {"tea": 1}, "r.jpg")
    claim = w.hr.claims[r.claim_id]
    assert claim.amount == Money.of(2000, "INR")     # we send what the receipt says
    w.hr.approve(claim.id)
    assert claim.paid == Money.of(250, "NOK")        # HR pays in payroll currency
    # budget accounting stays in the office's currency
    assert w.svc.budget.spent(BLR, (2026, 11)) == Money.of(2000, "INR")


def test_rejected_claim_alerts_managers(world):
    r = world.svc.report_empty(OSLO)
    world.buy(r, r.offered_to[0], 400, "NOK")
    world.hr.reject(r.claim_id)
    world.svc.tick()
    assert r.state == State.CLAIM_REJECTED
    assert world.chat.of_kind("rejected")
