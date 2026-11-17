import threading

import pytest

from snackcounter.models import State
from snackcounter.refill_service import AlreadyTaken, NotOffered
from conftest import OSLO


def test_second_volunteer_cannot_commit_same_refill(world):
    r = world.svc.report_empty(OSLO)
    a, b = r.offered_to[:2]
    world.svc.commit(r.id, a)
    with pytest.raises(AlreadyTaken):
        world.svc.commit(r.id, b)
    assert r.assignee == a
    assert any(m.to == b and m.kind == "taken" for m in world.chat.messages)


def test_many_concurrent_commits_only_one_wins(world):
    r = world.svc.report_empty(OSLO)
    results = []

    def go(vid):
        try:
            world.svc.commit(r.id, vid)
            results.append("ok")
        except (AlreadyTaken, NotOffered):
            results.append("rejected")

    threads = [threading.Thread(target=go, args=(vid,)) for vid in r.offered_to * 10]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count("ok") == 1
    assert r.state == State.COMMITTED


def test_only_offered_volunteers_may_commit(world):
    r = world.svc.report_empty(OSLO)
    with pytest.raises(NotOffered):
        world.svc.commit(r.id, "b1")          # Bengaluru person, wrong office


def test_double_empty_report_creates_one_refill(world):
    assert world.svc.report_empty(OSLO) is world.svc.report_empty(OSLO)
    assert len(world.svc.refills) == 1
    world.svc.commit(1, world.svc.refills[1].offered_to[0])
    assert world.svc.report_empty(OSLO).id == 1      # still the same open refill
