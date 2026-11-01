"""Data types for recurring-bill detection.

All money is ``Decimal``. Amounts follow Plaid's sign convention: positive means
money left the account, negative means money came in (refunds, deposits).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum


class Frequency(StrEnum):
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMIANNUAL = "semiannual"
    ANNUAL = "annual"
    IRREGULAR = "irregular"
    UNKNOWN = "unknown"


class BillStatus(StrEnum):
    ACTIVE = "active"
    # Too little evidence (seen once, or too little history): might be a bill,
    # the user has to tell us.
    POSSIBLE = "possible"
    # Stopped appearing for two or more cycles. Kept for the record, never alarmed on.
    STOPPED = "stopped"


class Severity(StrEnum):
    # Goes in the "Needs your attention" bucket.
    REVIEW = "review"
    # Shown as context, needs nothing from the user.
    INFO = "info"


class FlagKind(StrEnum):
    DOUBLE_CHARGE = "possible_double_charge"
    AMOUNT_CHANGED = "amount_changed"
    FORGOTTEN_SUBSCRIPTION = "possible_forgotten_subscription"
    YEARLY_CHARGE = "yearly_charge"
    IRREGULAR_SCHEDULE = "irregular_schedule"
    EXPECTED_CHARGE_MISSING = "expected_charge_missing"
    LOW_CONFIDENCE = "not_sure_this_is_a_bill"
    SEEN_ONCE = "possible_bill_seen_once"
    UNREADABLE_TRANSACTION = "unreadable_transaction"
    NOT_ENOUGH_HISTORY = "not_enough_history"
    MULTIPLE_ACCOUNTS = "paid_from_multiple_accounts"
    NAME_CHANGED = "payee_name_changed"
    REFUND_EXCLUDED = "refund_excluded"


@dataclass(frozen=True)
class Transaction:
    id: str
    account_id: str
    amount: Decimal
    date: date
    name: str
    merchant_name: str | None = None
    category: str | None = None
    pending: bool = False


@dataclass(frozen=True)
class UnreadableTransaction:
    """A transaction we could not use because a field we rely on was missing or garbled."""

    id: str
    name: str
    amount: Decimal | None
    raw_date: str | None
    problem: str  # "date" or "amount"


@dataclass
class Flag:
    kind: FlagKind
    severity: Severity
    message: str
    transaction_ids: list[str] = field(default_factory=list)


@dataclass
class Bill:
    id: str
    payee: str
    payee_key: str
    frequency: Frequency
    status: BillStatus
    typical_amount: Decimal
    min_amount: Decimal
    max_amount: Decimal
    last_amount: Decimal
    last_date: date
    next_due: date | None
    # For irregular schedules the due date is a window, not a day.
    next_due_earliest: date | None
    next_due_latest: date | None
    confidence: float
    occurrences: int
    account_ids: list[str]
    transaction_ids: list[str]
    category: str | None
    reasons: list[str] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return any(f.severity is Severity.REVIEW for f in self.flags)


@dataclass
class DetectionResult:
    as_of: date
    history_days: int
    bills: list[Bill]
    # Flags that do not belong to any one bill (e.g. not enough history).
    flags: list[Flag]
