"""Money as integer minor units (øre / paise). Never floats: totals must add up exactly."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


@dataclass(frozen=True)
class Money:
    minor: int
    currency: str

    @classmethod
    def of(cls, major, currency: str) -> "Money":
        minor = (Decimal(str(major)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        return cls(int(minor), currency)

    @classmethod
    def zero(cls, currency: str) -> "Money":
        return cls(0, currency)

    def _check(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError(f"currency mismatch: {self.currency} vs {other.currency}")

    def __add__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.minor + other.minor, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.minor - other.minor, self.currency)

    def __le__(self, other: "Money") -> bool:
        self._check(other)
        return self.minor <= other.minor

    def __lt__(self, other: "Money") -> bool:
        self._check(other)
        return self.minor < other.minor

    def __str__(self) -> str:
        return f"{Decimal(self.minor) / 100:.2f} {self.currency}"


class RateTable:
    """Fixed, configurable rates: value of 1 major unit of a currency in the base currency.

    Real FX feed is deliberately out of scope; the report states which rates it used.
    """

    def __init__(self, base: str, rates: dict[str, Decimal | str]):
        self.base = base
        self.rates = {c: Decimal(str(r)) for c, r in rates.items()}
        self.rates[base] = Decimal(1)

    def convert(self, m: Money, to: str) -> Money:
        if m.currency == to:
            return m
        value = Decimal(m.minor) * self.rates[m.currency] / self.rates[to]
        return Money(int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP)), to)
