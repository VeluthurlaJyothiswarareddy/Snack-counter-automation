from datetime import timedelta

from snackcounter.models import Config, State
from snackcounter.money import Money
from conftest import OSLO, BLR, World


def test_fewest_recent_refills_is_asked_first():
    w = World(Config(batch_size=1))
    r = w.svc.report_empty(OSLO)
    first = r.offered_to[0]
    w.buy(r, first, 500, "NOK")
    w.hr.approve(r.claim_id); w.svc.tick()
    r2 = w.svc.report_empty(OSLO)
    assert r2.offered_to[0] != first        # someone who hasn't done one yet goes first


def test_person_out_of_pocket_too_long_is_skipped():
    w = World(Config(batch_size=1, exposure_cap=Money.of(1000, "NOK")))
    r = w.svc.report_empty(OSLO)
    rich = r.offered_to[0]
    w.buy(r, rich, 1100, "NOK")             # claim stays unapproved -> exposure 1100 >= cap
    for _ in range(3):
        r = w.svc.report_empty(OSLO)
        assert rich not in r.offered_to
        w.buy(r, r.offered_to[0], 300, "NOK")


def test_exposure_counts_both_currencies_in_base():
    w = World()
    r = w.svc.report_empty(BLR)
    v = r.offered_to[0]
    w.buy(r, v, 2000, "INR")
    assert w.svc.exposure(v) == Money.of(250, "NOK")


def test_volunteer_on_holiday_is_not_asked_until_back():
    w = World(Config(batch_size=4))
    w.volunteer("o1").away_until = w.clock.now() + timedelta(days=7)
    r = w.svc.report_empty(OSLO)
    assert "o1" not in r.offered_to
    w.svc.commit(r.id, r.offered_to[0])
    w.clock.advance(days=8)
    w.svc.tick()    # deadline passed -> reoffered; o1 is back now
    assert "o1" in r.offered_to


def test_visitor_is_asked_for_the_office_they_are_in_not_home():
    w = World(Config(batch_size=10))
    visitor = w.volunteer("o1")
    visitor.current_office = BLR
    assert "o1" not in w.svc.report_empty(OSLO).offered_to
    assert "o1" in w.svc.report_empty(BLR).offered_to


def test_nobody_available_escalates_immediately():
    w = World()
    for v in w.volunteers:
        v.away_until = w.clock.now() + timedelta(days=3)
    r = w.svc.report_empty(OSLO)
    assert r.state == State.ESCALATED
    assert w.chat.of_kind("escalation")
