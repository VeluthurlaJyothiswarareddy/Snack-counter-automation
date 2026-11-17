import pytest

from snackcounter.adapters.chat import FakeChat
from snackcounter.adapters.hr import FakeHR
from snackcounter.clock import FakeClock
from snackcounter.models import Config, Office, Volunteer
from snackcounter.money import Money, RateTable
from snackcounter.refill_service import RefillService

OSLO, BLR = "Oslo", "Bengaluru"


def make_offices():
    return {
        OSLO: Office(OSLO, "NOK", Money.of(6000, "NOK"), Money.of(1200, "NOK")),
        BLR: Office(BLR, "INR", Money.of(15000, "INR"), Money.of(3000, "INR")),
    }


def make_volunteers():
    vs = [Volunteer(f"o{i}", f"Oslo{i}", OSLO, OSLO, "NOK") for i in range(1, 5)]
    vs += [Volunteer(f"b{i}", f"Blr{i}", BLR, BLR, "INR") for i in range(1, 5)]
    return vs


class World:
    def __init__(self, config=Config()):
        self.rates = RateTable("NOK", {"INR": "0.125"})   # 1 INR = 0.125 NOK
        self.clock, self.chat = FakeClock(), FakeChat()
        self.volunteers = make_volunteers()
        self.hr = FakeHR({v.id: v.payroll_currency for v in self.volunteers}, self.rates)
        self.svc = RefillService(make_offices(), self.volunteers, self.chat, self.hr,
                                 self.clock, self.rates, config)

    def volunteer(self, vid):
        return next(v for v in self.volunteers if v.id == vid)

    def buy(self, refill, vid, amount, currency, items=None):
        """Offered -> committed -> purchased for the given volunteer."""
        self.svc.commit(refill.id, vid)
        return self.svc.complete_purchase(refill.id, vid, Money.of(amount, currency),
                                          items or {"chips": 3}, "receipt.jpg")


@pytest.fixture
def world():
    return World()
