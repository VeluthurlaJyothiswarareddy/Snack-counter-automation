from datetime import timedelta

import pytest

from snackcounter.models import State
from snackcounter.refill_service import NotOffered
from conftest import OSLO


def test_uncompleted_refill_is_handed_to_someone_else(world):
    r = world.svc.report_empty(OSLO)
    first = r.offered_to[0]
    world.svc.commit(r.id, first)
    world.clock.advance(hours=25)             # past the 24h purchase deadline
    world.svc.tick()
    assert r.state == State.OFFERED and r.assignee is None
    assert first in r.excluded and first not in r.offered_to
    assert r.offered_to                        # someone new has been asked
    assert any(m.to == first and m.kind == "reassigned" for m in world.chat.messages)
    with pytest.raises(NotOffered):
        world.svc.commit(r.id, first)          # failed volunteer can't grab it back


def test_nothing_happens_before_deadline(world):
    r = world.svc.report_empty(OSLO)
    v = r.offered_to[0]
    world.svc.commit(r.id, v)
    world.clock.advance(hours=23)
    world.svc.tick()
    assert r.state == State.COMMITTED and r.assignee == v


def test_unanswered_offer_moves_on_to_next_batch(world):
    r = world.svc.report_empty(OSLO)
    first_batch = list(r.offered_to)
    world.clock.advance(hours=3)
    world.svc.tick()
    assert set(r.offered_to).isdisjoint(first_batch) and r.offered_to


def test_all_decline_or_ignore_escalates_to_managers_then_retries(world):
    r = world.svc.report_empty(OSLO)
    for _ in range(5):
        world.clock.advance(hours=3)
        world.svc.tick()
        if r.state == State.ESCALATED:
            break
    assert r.state == State.ESCALATED
    assert len(world.chat.of_kind("escalation")) == 1
    world.svc.tick()                           # everyone gets another chance
    assert r.state == State.OFFERED


def test_decline_hands_over_immediately(world):
    r = world.svc.report_empty(OSLO)
    for v in list(r.offered_to):
        world.svc.decline(r.id, v)
    assert r.offered_to and not set(r.offered_to) & r.excluded


def test_released_commitment_frees_the_budget_reservation(world):
    r = world.svc.report_empty(OSLO)
    world.svc.commit(r.id, r.offered_to[0])
    assert world.svc.budget.reserved(OSLO).minor == 120000
    world.clock.advance(hours=25)
    world.svc.tick()
    assert world.svc.budget.reserved(OSLO).minor == 0
