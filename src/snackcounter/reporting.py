"""One monthly report across both offices.

Native-currency numbers are exact; the combined total converts each currency's *sum* once
(not each purchase), with the stated rates, to avoid accumulating rounding error.
"""
from __future__ import annotations

from .budget import BudgetLedger
from .money import Money, RateTable


def monthly_report(ledger: BudgetLedger, rates: RateTable, month: tuple[int, int],
                   items_by_office: dict[str, dict[str, int]] | None = None) -> dict:
    offices = {}
    totals_by_currency: dict[str, Money] = {}
    for name, o in ledger.offices.items():
        spent = ledger.spent(name, month)
        offices[name] = {
            "spent": spent,
            "budget": o.monthly_budget,
            "remaining": o.monthly_budget - spent,
            "over_budget": o.monthly_budget < spent,
            "items": (items_by_office or {}).get(name, {}),
        }
        totals_by_currency[o.currency] = totals_by_currency.get(o.currency, Money.zero(o.currency)) + spent
    total = Money.zero(rates.base)
    for m in totals_by_currency.values():
        total = total + rates.convert(m, rates.base)
    return {"month": month, "offices": offices, "total": total,
            "rates_used": {c: str(r) for c, r in rates.rates.items()}}
