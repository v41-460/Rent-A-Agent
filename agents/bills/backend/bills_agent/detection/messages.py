"""Plain-English wording for everything the detector tells the user.

Every number in these sentences is computed by the detector and passed in;
this module only formats.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from .models import Frequency

FREQUENCY_WORDS = {
    Frequency.WEEKLY: "every week",
    Frequency.BIWEEKLY: "every two weeks",
    Frequency.MONTHLY: "every month",
    Frequency.QUARTERLY: "every three months",
    Frequency.SEMIANNUAL: "every six months",
    Frequency.ANNUAL: "once a year",
}


def money(amount: Decimal) -> str:
    return f"${amount:,.2f}"


def day(d: date, as_of: date | None = None) -> str:
    text = f"{d:%b} {d.day}"
    if as_of is None or d.year != as_of.year:
        text += f", {d.year}"
    return text


def month(d: date) -> str:
    return f"{d:%B %Y}"


def times(n: int) -> str:
    return {1: "once", 2: "twice"}.get(n, f"{n} times")
