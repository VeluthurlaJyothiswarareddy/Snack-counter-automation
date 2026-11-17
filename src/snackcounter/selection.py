"""Choosing who buys. Pure function: easy to test, easy to explain.

Eligible: physically at (or assigned to) the refill's office *now* (visitors count, their
home office doesn't), not away, not already tried for this refill, and not already too far
out of pocket waiting for HR.
Ranking (fairness): fewest refills in the recent window, then lowest unreimbursed exposure,
then longest since last refill, then id (stable tie-break).
"""
from __future__ import annotations

from datetime import datetime

from .models import Refill, Volunteer


def rank_candidates(
    refill: Refill,
    volunteers: list[Volunteer],
    now: datetime,
    recent_counts: dict[str, int],
    exposure_base_minor: dict[str, int],
    last_refill_at: dict[str, datetime],
    exposure_cap_minor: int,
) -> list[Volunteer]:
    eligible = [
        v for v in volunteers
        if v.current_office == refill.office
        and v.id not in refill.excluded
        and (v.away_until is None or v.away_until <= now)
        and exposure_base_minor.get(v.id, 0) < exposure_cap_minor
    ]
    epoch = datetime.min.replace(tzinfo=now.tzinfo)
    return sorted(
        eligible,
        key=lambda v: (
            recent_counts.get(v.id, 0),
            exposure_base_minor.get(v.id, 0),
            last_refill_at.get(v.id, epoch),
            v.id,
        ),
    )
