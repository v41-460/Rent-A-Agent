"""Helpers for writing realistic transaction histories in Plaid's shape.

Everything is seeded, so a scenario produces exactly the same transactions on
every run.
"""

from __future__ import annotations

import calendar
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

CHECKING = "acc_checking"
SAVINGS = "acc_savings"
CREDIT_CARD = "acc_card"

ACCOUNT_NAMES = {
    CHECKING: "Checking (...1111)",
    SAVINGS: "Savings (...2222)",
    CREDIT_CARD: "Credit card (...3333)",
}

_RESTAURANTS = [
    "CHIPOTLE 1187",
    "OLIVE GARDEN #445",
    "PANERA BREAD #2020",
    "TST* MAIN ST DINER",
    "CRACKER BARREL #312",
    "SUBWAY 30311",
    "DENNY'S #7781",
    "RED LOBSTER 0255",
]


@dataclass
class History:
    seed: int
    txs: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)

    def add(
        self,
        when: date | str | None,
        name: str,
        amount: float | str | None,
        *,
        account: str = CHECKING,
        merchant: str | None = None,
        category: str | None = None,
        pending: bool = False,
    ) -> dict[str, Any]:
        tx: dict[str, Any] = {
            "transaction_id": f"tx_{self.seed}_{len(self.txs):04d}",
            "account_id": account,
            "amount": amount if amount is None or isinstance(amount, str) else round(amount, 2),
            "date": when.isoformat() if isinstance(when, date) else when,
            "name": name,
            "merchant_name": merchant,
            "pending": pending,
        }
        if category:
            tx["personal_finance_category"] = {"primary": category}
        self.txs.append(tx)
        return tx

    def monthly(
        self,
        name: str,
        amounts: float | list[float],
        *,
        day: int,
        start: tuple[int, int],
        count: int,
        jitter: int = 0,
        accounts: list[str] | None = None,
        category: str | None = None,
        merchant: str | None = None,
    ) -> list[dict[str, Any]]:
        """One charge per calendar month on about the same day."""
        out = []
        year, month = start
        for i in range(count):
            amount = amounts[i] if isinstance(amounts, list) else amounts
            last_day = calendar.monthrange(year, month)[1]
            when = date(year, month, min(day, last_day))
            if jitter:
                when += timedelta(days=self.rng.randint(-jitter, jitter))
            account = accounts[i % len(accounts)] if accounts else CHECKING
            out.append(
                self.add(when, name, amount, account=account, category=category, merchant=merchant)
            )
            month += 1
            if month > 12:
                year, month = year + 1, 1
        return out

    def everyday_spending(self, start: date, end: date) -> None:
        """Groceries, fuel, coffee, eating out, online shopping and a paycheck.

        None of this is a bill. It is here so detection is always tested against
        the kind of noise a real account has.
        """
        self._repeat(
            start,
            end,
            (3, 9),
            lambda d: self.add(d, "KROGER #0423", self._cents(35, 190), category="FOOD_AND_DRINK"),
        )
        self._repeat(
            start,
            end,
            (4, 13),
            lambda d: self.add(
                d, "SHELL OIL 57444", self._cents(25, 65), category="TRANSPORTATION"
            ),
        )
        self._repeat(
            start,
            end,
            (1, 4),
            lambda d: self.add(
                d, "STARBUCKS STORE 10234", self._cents(4, 9), category="FOOD_AND_DRINK"
            ),
        )
        self._repeat(
            start,
            end,
            (2, 8),
            lambda d: self.add(
                d, self.rng.choice(_RESTAURANTS), self._cents(12, 75), category="FOOD_AND_DRINK"
            ),
        )
        self._repeat(
            start,
            end,
            (6, 20),
            lambda d: self.add(
                d,
                f"AMZN Mktp US*{self._code()}",
                self._cents(10, 120),
                merchant="Amazon",
                category="GENERAL_MERCHANDISE",
                account=CREDIT_CARD,
            ),
        )
        # Paycheck every two weeks: money in, never a bill.
        d = start + timedelta(days=4)
        while d <= end:
            self.add(d, "ACME CORP PAYROLL", -2150.00, category="INCOME")
            d += timedelta(days=14)
        # A transfer to savings each month: moving your own money is not a bill.
        d = start
        while d <= end:
            self.add(d, "ONLINE TRANSFER TO SAV ...2222", 200.00, category="TRANSFER_OUT")
            d = (d.replace(day=1) + timedelta(days=32)).replace(day=2)

    def _repeat(self, start: date, end: date, gap: tuple[int, int], make) -> None:
        d = start + timedelta(days=self.rng.randint(0, gap[1]))
        while d <= end:
            make(d)
            d += timedelta(days=self.rng.randint(*gap))

    def _cents(self, low: int, high: int) -> float:
        return round(self.rng.uniform(low, high), 2)

    def _code(self) -> str:
        return "".join(self.rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
