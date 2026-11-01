"""Recurring-bill detection.

Deterministic: the same transactions and the same ``as_of`` date always give the
same result. No LLM is involved in anything here; every amount, date and
comparison is computed in this file.

Pipeline:
  1. parse         unreadable rows are set aside and reported, never guessed at
  2. filter        drop pending rows, transfers and income
  3. refunds       a refund cancels out the matching charge
  4. group         by normalized payee; merge a payee whose name drifted
  5. split         one payee with two concurrent bills (e.g. auto + home insurance)
  6. analyze       duplicates, cadence, amount stability, next due date, status
  7. flag          anything uncertain or unusual is surfaced for review
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from statistics import median
from typing import Any

from dateutil.relativedelta import relativedelta

from . import messages as msg
from .models import (
    Bill,
    BillStatus,
    DetectionResult,
    Flag,
    FlagKind,
    Frequency,
    Severity,
    Transaction,
    UnreadableTransaction,
)
from .normalize import Payee, normalize_payee
from .parse import parse_transactions

# Plaid personal_finance_category.primary values that are never bills.
EXCLUDED_CATEGORIES = frozenset({"TRANSFER_IN", "TRANSFER_OUT", "INCOME"})
# Categories where a single charge is a strong hint of a bill.
BILL_CATEGORIES = frozenset({"RENT_AND_UTILITIES", "LOAN_PAYMENTS"})
# Categories whose bills vary month to month (usage, seasons, statement balances).
VARIABLE_BILL_CATEGORIES = frozenset({"RENT_AND_UTILITIES", "LOAN_PAYMENTS", "MEDICAL"})
# Categories that are necessities, never "a subscription you forgot about".
ESSENTIAL_CATEGORIES = frozenset(
    {"RENT_AND_UTILITIES", "LOAN_PAYMENTS", "MEDICAL", "GOVERNMENT_AND_NON_PROFIT", "BANK_FEES"}
)
BILL_WORDS = re.compile(
    r"\b(SUBSCRIPTION|MEMBERSHIP|RENEWAL|ANNUAL|YEARLY|MONTHLY|INSURANCE|PREMIUM|RENT|"
    r"AUTOPAY|AUTO PAY|UTILITY|UTILITIES|MORTGAGE|LOAN)\b"
)
YEARLY_WORDS = re.compile(r"\b(ANNUAL|YEARLY|RENEWAL)\b")

MIN_HISTORY_DAYS = 60
FORGOTTEN_SUBSCRIPTION_MAX = Decimal("20.00")
SPIKE_RATIO = Decimal("1.5")
SPIKE_MIN_DIFFERENCE = Decimal("10.00")
# How close charges must be to count as the same fixed price (taxes, rounding).
FIXED_PRICE_BAND = Decimal("0.02")
LOW_CONFIDENCE = 0.6
RECENT_DOUBLE_CHARGE_DAYS = 90
SEEN_ONCE_RECENT_DAYS = 45
SEEN_ONCE_YEARLY_DAYS = 380
REFUND_MATCH_DAYS = 45


@dataclass(frozen=True)
class Cadence:
    frequency: Frequency
    nominal_days: float
    tolerance_days: int
    months: int | None  # calendar step, when the bill follows the calendar


CADENCES = [
    Cadence(Frequency.WEEKLY, 7, 2, None),
    Cadence(Frequency.BIWEEKLY, 14, 3, None),
    Cadence(Frequency.MONTHLY, 30.44, 6, 1),
    Cadence(Frequency.QUARTERLY, 91.31, 12, 3),
    Cadence(Frequency.SEMIANNUAL, 182.62, 15, 6),
    Cadence(Frequency.ANNUAL, 365.25, 20, 12),
]


@dataclass
class _Series:
    key: str
    payee: Payee
    txs: list[Transaction]
    ordinal: int = 0
    rename_note: str | None = None
    refund_notes: list[str] = field(default_factory=list)


@dataclass
class _Context:
    as_of: date
    history_days: int
    account_names: Mapping[str, str]

    def account(self, account_id: str) -> str:
        return self.account_names.get(account_id, "another account")


def detect_bills(
    raw_transactions: Iterable[Mapping[str, Any]],
    as_of: date,
    account_names: Mapping[str, str] | None = None,
) -> DetectionResult:
    parsed, unreadable = parse_transactions(raw_transactions)
    dated = [t.date for t in parsed]
    history_days = (as_of - min(dated)).days if dated else 0
    ctx = _Context(as_of, history_days, account_names or {})

    usable = [
        t
        for t in parsed
        if not t.pending and t.category not in EXCLUDED_CATEGORIES and t.date <= as_of
    ]
    payees = {t.id: normalize_payee(t.name, t.merchant_name) for t in usable}
    outflows = [t for t in usable if t.amount > 0]
    inflows = [t for t in usable if t.amount < 0]

    outflows, refund_notes = _remove_refunded(outflows, inflows, payees, ctx)
    groups = _group(outflows, payees)
    _merge_renamed(groups, ctx)

    bills: list[Bill] = []
    for series in groups.values():
        series.refund_notes = refund_notes.get(series.key, [])
        bills += _analyze_payee(series, ctx)

    global_flags = _attach_unreadable(unreadable, bills, ctx)
    if history_days < MIN_HISTORY_DAYS:
        global_flags.insert(
            0,
            Flag(
                FlagKind.NOT_ENOUGH_HISTORY,
                Severity.REVIEW,
                f"I can only see {history_days} days of your history so far. Most bills "
                f"come once a month, so I need about two months to spot them reliably. "
                f"I'll keep checking as more comes in.",
            ),
        )

    bills.sort(key=lambda b: (b.status is BillStatus.STOPPED, b.next_due or date.max, b.payee))
    return DetectionResult(as_of=as_of, history_days=history_days, bills=bills, flags=global_flags)


# --- refunds ---------------------------------------------------------------


def _remove_refunded(
    outflows: list[Transaction],
    inflows: list[Transaction],
    payees: Mapping[str, Payee],
    ctx: _Context,
) -> tuple[list[Transaction], dict[str, list[str]]]:
    """A refund for exactly the same amount from the same payee cancels the charge."""
    by_key: dict[str, list[Transaction]] = defaultdict(list)
    for t in outflows:
        by_key[payees[t.id].key].append(t)
    removed: set[str] = set()
    notes: dict[str, list[str]] = defaultdict(list)
    for refund in sorted(inflows, key=lambda t: (t.date, t.id)):
        key = payees[refund.id].key
        matches = [
            t
            for t in by_key.get(key, [])
            if t.id not in removed
            and t.amount == -refund.amount
            and t.date <= refund.date <= t.date + timedelta(days=REFUND_MATCH_DAYS)
        ]
        if not matches:
            continue
        charge = max(matches, key=lambda t: (t.date, t.id))
        removed.add(charge.id)
        notes[key].append(
            f"A {msg.money(charge.amount)} charge on {msg.day(charge.date, ctx.as_of)} was "
            f"refunded on {msg.day(refund.date, ctx.as_of)}, so I haven't counted it."
        )
    return [t for t in outflows if t.id not in removed], notes


# --- grouping --------------------------------------------------------------


def _group(outflows: list[Transaction], payees: Mapping[str, Payee]) -> dict[str, _Series]:
    groups: dict[str, _Series] = {}
    for t in sorted(outflows, key=lambda t: (t.date, t.id)):
        payee = payees[t.id]
        if payee.key in groups:
            groups[payee.key].txs.append(t)
            # The most recent descriptor wins the display name.
            groups[payee.key].payee = payee
        else:
            groups[payee.key] = _Series(payee.key, payee, [t])
    return groups


def _merge_renamed(groups: dict[str, _Series], ctx: _Context) -> None:
    """Merge a payee whose bank descriptor changed, e.g. "SQ *GREENLEAF LAWN" became
    "GREENLEAF LAWN CARE LLC".

    Only merges when every check passes: one name is the start of exactly one other
    name, the two never appear at the same time, and the amounts are similar.
    """
    changed = True
    while changed:
        changed = False
        for short in sorted(groups):
            words = short.split()
            if len(words) == 1 and len(short) < 5:
                continue
            longer = [k for k in groups if k != short and k.split()[: len(words)] == words]
            if len(longer) != 1:
                continue
            a, b = groups[short], groups[longer[0]]
            a_dates = [t.date for t in a.txs]
            b_dates = [t.date for t in b.txs]
            if max(a_dates) < min(b_dates):
                old, new = a, b
            elif max(b_dates) < min(a_dates):
                old, new = b, a
            else:
                continue
            a_mid = _median_money([t.amount for t in a.txs])
            b_mid = _median_money([t.amount for t in b.txs])
            if abs(a_mid - b_mid) > Decimal("0.25") * max(a_mid, b_mid):
                continue
            switch = min(t.date for t in new.txs)
            new.txs = sorted(old.txs + new.txs, key=lambda t: (t.date, t.id))
            new.rename_note = (
                f"The name on this charge changed from “{old.payee.display}” to "
                f"“{new.payee.display}” in {msg.month(switch)}. The amount and timing "
                f"match, so I've treated them as the same bill."
            )
            del groups[old.key]
            changed = True
            break


def _split_concurrent(series: _Series) -> list[_Series]:
    """Split one payee into separate bills when it charges two different amounts in
    the same months, e.g. an insurer billing auto and home separately."""
    by_amount = sorted(series.txs, key=lambda t: t.amount)
    clusters: list[list[Transaction]] = [[by_amount[0]]]
    for t in by_amount[1:]:
        prev = clusters[-1][-1].amount
        if (t.amount - prev) <= Decimal("0.15") * prev:
            clusters[-1].append(t)
        else:
            clusters.append([t])
    big = [c for c in clusters if len(c) >= 3]
    if len(big) < 2:
        return [series]
    months = [{(t.date.year, t.date.month) for t in c} for c in big]
    for i in range(len(big)):
        for j in range(i + 1, len(big)):
            if len(months[i] & months[j]) < 2:
                return [series]

    medians = [_median_money([t.amount for t in c]) for c in big]
    parts: list[list[Transaction]] = [list(c) for c in big]
    for c in clusters:
        if len(c) >= 3:
            continue
        for t in c:
            nearest = min(range(len(big)), key=lambda i: abs(medians[i] - t.amount))
            parts[nearest].append(t)
    return [
        _Series(
            series.key,
            series.payee,
            sorted(p, key=lambda t: (t.date, t.id)),
            ordinal=i,
            rename_note=series.rename_note,
            refund_notes=series.refund_notes if i == 0 else [],
        )
        for i, p in enumerate(parts)
    ]


# --- analysis --------------------------------------------------------------


def _analyze_payee(series: _Series, ctx: _Context) -> list[Bill]:
    whole = _analyze(series, ctx)
    parts = _split_concurrent(series)
    if len(parts) == 1:
        return [whole] if whole else []
    # Splitting one payee into two bills is a strong claim. Only make it when the
    # charges make no sense as one bill and each part is a proper bill on its own.
    split = [_analyze(p, ctx) for p in parts]
    if whole is None and all(b is not None and b.status is BillStatus.ACTIVE for b in split):
        return [b for b in split if b is not None]
    return [whole] if whole else []


def _analyze(series: _Series, ctx: _Context) -> Bill | None:
    kept, dupes = _split_duplicates(series.txs)
    if len(kept) == 1 or ctx.history_days < MIN_HISTORY_DAYS:
        # Too little to go on. At most, ask about charges that look like bills.
        return _possible_bill(series, kept, dupes, ctx)

    amounts = [t.amount for t in kept]
    intervals = [(b.date - a.date).days for a, b in zip(kept, kept[1:], strict=False)]
    cadence, gaps = _classify([t.date for t in kept])
    if cadence is not None:
        frequency = cadence.frequency
    elif _is_irregular(intervals):
        frequency = Frequency.IRREGULAR
    else:
        return None
    model = _amount_model(amounts, frequency, _category(series.txs))
    if model is None:
        return None
    typical = model.typical

    last = kept[-1]
    earliest = latest = None
    if cadence is None:
        earliest = last.date + timedelta(days=min(intervals))
        latest = last.date + timedelta(days=max(intervals))
        next_due = last.date + timedelta(days=round(median(intervals)))
        expected_by, cycle_days, grace = latest, median(intervals), 7
    else:
        if cadence.months:
            next_due = last.date + relativedelta(months=cadence.months)
        else:
            next_due = last.date + timedelta(days=round(cadence.nominal_days))
        expected_by, cycle_days, grace = next_due, cadence.nominal_days, cadence.tolerance_days + 3

    missed = ctx.as_of > expected_by + timedelta(days=grace)
    stopped = ctx.as_of > expected_by + timedelta(days=round(cycle_days) + grace)

    confidence = _confidence(frequency, len(kept), gaps, amounts, typical, series, ctx)
    accounts = sorted({t.account_id for t in series.txs})
    bill = Bill(
        id=_bill_id(series),
        payee=series.payee.display,
        payee_key=series.key,
        frequency=frequency,
        status=BillStatus.STOPPED if stopped else BillStatus.ACTIVE,
        typical_amount=typical,
        min_amount=min(amounts),
        max_amount=max(amounts),
        last_amount=last.amount,
        last_date=last.date,
        next_due=None if stopped else next_due,
        next_due_earliest=None if stopped else earliest,
        next_due_latest=None if stopped else latest,
        confidence=confidence,
        occurrences=len(kept),
        account_ids=accounts,
        transaction_ids=[t.id for t in series.txs],
        category=_category(series.txs),
        reasons=_reasons(kept, frequency, intervals, model, gaps, ctx),
    )

    if stopped:
        bill.flags.append(
            Flag(
                FlagKind.EXPECTED_CHARGE_MISSING,
                Severity.INFO,
                f"The last charge was on {msg.day(last.date, ctx.as_of)}. It looks like this "
                f"has stopped, so I've moved it out of your upcoming bills.",
            )
        )
        return bill

    bill.flags += _duplicate_flags(series, dupes, ctx)
    bill.flags += _amount_flags(series, kept, model, ctx)
    if (
        frequency is Frequency.MONTHLY
        and typical <= FORGOTTEN_SUBSCRIPTION_MAX
        and not series.payee.well_known
        and bill.category not in ESSENTIAL_CATEGORIES
    ):
        bill.flags.append(
            Flag(
                FlagKind.FORGOTTEN_SUBSCRIPTION,
                Severity.REVIEW,
                f"You've been paying {series.payee.display} {msg.money(typical)} every month "
                f"since {msg.month(kept[0].date)}. If you don't recognize this or no longer "
                f"use it, it may be worth cancelling.",
                [t.id for t in kept],
            )
        )
    if frequency is Frequency.ANNUAL:
        bill.flags.append(
            Flag(
                FlagKind.YEARLY_CHARGE,
                Severity.REVIEW,
                f"This is a yearly charge of about {msg.money(typical)}, last paid on "
                f"{msg.day(last.date, ctx.as_of)}. I expect the next one around "
                f"{msg.day(next_due, ctx.as_of)}. Yearly bills are easy to forget, so please "
                f"check you still want it.",
                [t.id for t in kept],
            )
        )
    if frequency is Frequency.IRREGULAR:
        assert earliest is not None and latest is not None
        bill.flags.append(
            Flag(
                FlagKind.IRREGULAR_SCHEDULE,
                Severity.REVIEW,
                f"This doesn't come on a fixed schedule, {_week_range(intervals)} apart. "
                f"I expect the next one between {msg.day(earliest, ctx.as_of)} and "
                f"{msg.day(latest, ctx.as_of)}, but I can't be exact.",
            )
        )
    if missed:
        bill.flags.append(
            Flag(
                FlagKind.EXPECTED_CHARGE_MISSING,
                Severity.REVIEW,
                f"I expected a charge from {series.payee.display} around "
                f"{msg.day(expected_by, ctx.as_of)} but haven't seen one. If you've cancelled "
                f"it or paid it another way, you can ignore this.",
            )
        )
    if confidence < LOW_CONFIDENCE:
        bill.flags.append(
            Flag(
                FlagKind.LOW_CONFIDENCE,
                Severity.REVIEW,
                f"I've only seen this {msg.times(len(kept))}, so I'm not fully sure it's a "
                f"regular bill yet.",
            )
        )
    if len(accounts) > 1:
        bill.flags.append(
            Flag(
                FlagKind.MULTIPLE_ACCOUNTS,
                Severity.INFO,
                f"You've paid this from {len(accounts)} different accounts. I've counted it as "
                f"one bill.",
            )
        )
    if series.rename_note:
        bill.flags.append(Flag(FlagKind.NAME_CHANGED, Severity.INFO, series.rename_note))
    for note in series.refund_notes:
        bill.flags.append(Flag(FlagKind.REFUND_EXCLUDED, Severity.INFO, note))
    return bill


def _split_duplicates(
    txs: list[Transaction],
) -> tuple[list[Transaction], list[tuple[Transaction, Transaction]]]:
    """Separate charges that repeat the previous one within a few days for the same amount."""
    gaps = [(b.date - a.date).days for a, b in zip(txs, txs[1:], strict=False)]
    window = max(1, min(7, round(0.2 * median(gaps)))) if gaps else 0
    kept: list[Transaction] = []
    dupes: list[tuple[Transaction, Transaction]] = []
    for t in txs:
        prev = kept[-1] if kept else None
        if (
            prev is not None
            and (t.date - prev.date).days <= window
            and abs(t.amount - prev.amount) <= max(prev.amount * Decimal("0.02"), Decimal("0.01"))
        ):
            dupes.append((prev, t))
        else:
            kept.append(t)
    return kept, dupes


def _classify(dates: list[date]) -> tuple[Cadence | None, int]:
    """Match charge dates to a known cadence. One skipped cycle is tolerated when
    there is enough history around it."""
    allowed_gaps = 1 if len(dates) >= 4 else 0
    for cadence in CADENCES:
        gaps = 0
        for prev, cur in zip(dates, dates[1:], strict=False):
            steps = _steps(prev, cur, cadence)
            if steps is None:
                break
            gaps += steps == 2
        else:
            if gaps <= allowed_gaps:
                return cadence, gaps
    return None, 0


def _steps(prev: date, cur: date, cadence: Cadence) -> int | None:
    """1 if ``cur`` is one cycle after ``prev``, 2 if one cycle was skipped, else None.
    Monthly-style cadences step by calendar month, so February doesn't look early."""
    for k in (1, 2):
        if cadence.months:
            expected = prev + relativedelta(months=cadence.months * k)
        else:
            expected = prev + timedelta(days=round(cadence.nominal_days * k))
        if abs((cur - expected).days) <= cadence.tolerance_days * k:
            return k
    return None


@dataclass(frozen=True)
class _AmountModel:
    typical: Decimal
    # A fixed-price bill (subscription, insurance) rather than a usage-based one.
    fixed: bool
    # Index of the first charge at a new fixed price, when the price changed once.
    price_change_at: int | None = None


def _amount_model(
    amounts: list[Decimal], frequency: Frequency, category: str | None
) -> _AmountModel | None:
    """Is the amount steady enough for this to be a bill rather than repeat shopping?
    Returns how the amount behaves, or None if it doesn't behave like a bill."""
    variable = category in VARIABLE_BILL_CATEGORIES and frequency not in (
        Frequency.WEEKLY,
        Frequency.BIWEEKLY,
    )
    if len(amounts) == 2:
        # Two charges prove little. Two coffees a week apart are not a weekly bill, and
        # a fixed-price bill charges exactly the same amount, to the cent.
        if frequency in (Frequency.WEEKLY, Frequency.BIWEEKLY, Frequency.IRREGULAR):
            return None
        if not variable:
            return _AmountModel(amounts[1], fixed=True) if amounts[0] == amounts[1] else None
        if _share_within(amounts, _median_money(amounts), Decimal("0.1")) < 1:
            return None
        return _AmountModel(_median_money(amounts), fixed=False)

    # Judge the pattern on the earlier charges. The latest one is checked separately,
    # so a sudden jump gets flagged instead of hiding the bill.
    base = amounts[:-1] if len(amounts) >= 4 else amounts
    if variable:
        # Utilities and loan payments legitimately swing with the seasons or usage.
        band, needed = (
            (Decimal("0.2"), 0.75) if frequency is Frequency.IRREGULAR else (Decimal("0.5"), 0.7)
        )
        if _share_within(base, _median_money(base), band) < needed:
            return None
        return _AmountModel(_median_money(amounts), fixed=False)

    # Everything else must be a fixed price. Without this, a restaurant visited about
    # once a month, or weekly groceries, start to look like bills.
    if _share_within(base, _median_money(base), FIXED_PRICE_BAND) >= 0.8:
        return _AmountModel(_median_money(base), fixed=True)
    # A fixed price that changed once, like a subscription price rise.
    for i in range(2, len(amounts) - 1):
        before, after = amounts[:i], amounts[i:]
        if _is_fixed(before) and _is_fixed(after):
            return _AmountModel(_median_money(after), fixed=True, price_change_at=i)
    return None


def _is_fixed(amounts: list[Decimal]) -> bool:
    return _share_within(amounts, _median_money(amounts), FIXED_PRICE_BAND) == 1


def _is_irregular(intervals: list[int]) -> bool:
    """A real but loose rhythm, like a service every 4 to 6 weeks."""
    return (
        len(intervals) >= 3
        and min(intervals) >= 20
        and max(intervals) <= 70
        and max(intervals) <= 1.75 * min(intervals)
    )


def _confidence(
    frequency: Frequency,
    n: int,
    gaps: int,
    amounts: list[Decimal],
    typical: Decimal,
    series: _Series,
    ctx: _Context,
) -> float:
    if frequency in (Frequency.ANNUAL, Frequency.SEMIANNUAL):
        count = 0.8 if n == 2 else 0.9
    else:
        count = {2: 0.5, 3: 0.7, 4: 0.8, 5: 0.85}.get(n, 0.95)
    rhythm = 0.7 if frequency is Frequency.IRREGULAR else (0.85 if gaps else 1.0)
    band = Decimal("0.3") if _category(series.txs) in VARIABLE_BILL_CATEGORIES else Decimal("0.1")
    steady = _share_within(amounts, typical, band)
    amount = 1.0 if steady >= 0.9 else (0.9 if steady >= 0.6 else 0.8)
    score = count * rhythm * amount
    if series.rename_note:
        score *= 0.95
    if ctx.history_days < MIN_HISTORY_DAYS:
        score *= 0.6
    return round(score, 2)


def _duplicate_flags(
    series: _Series, dupes: list[tuple[Transaction, Transaction]], ctx: _Context
) -> list[Flag]:
    flags = []
    for first, second in dupes:
        if (ctx.as_of - second.date).days > RECENT_DOUBLE_CHARGE_DAYS:
            continue
        when = (
            f"on {msg.day(first.date, ctx.as_of)}"
            if first.date == second.date
            else f"on {msg.day(first.date, ctx.as_of)} and {msg.day(second.date, ctx.as_of)}"
        )
        if first.account_id != second.account_id:
            text = (
                f"{series.payee.display} was paid twice, {when}: {msg.money(first.amount)} from "
                f"{ctx.account(first.account_id)} and {msg.money(second.amount)} from "
                f"{ctx.account(second.account_id)}. One of these may be a mistake."
            )
        else:
            text = (
                f"{series.payee.display} charged you twice {when}, {msg.money(first.amount)} "
                f"each time. One of these may be a mistake."
            )
        flags.append(Flag(FlagKind.DOUBLE_CHARGE, Severity.REVIEW, text, [first.id, second.id]))
    return flags


def _amount_flags(
    series: _Series, kept: list[Transaction], model: _AmountModel, ctx: _Context
) -> list[Flag]:
    amounts = [t.amount for t in kept]
    name = series.payee.display
    if model.price_change_at is not None:
        i = model.price_change_at
        old, new = _median_money(amounts[:i]), _median_money(amounts[i:])
        changed = kept[i]
        return [
            Flag(
                FlagKind.AMOUNT_CHANGED,
                Severity.REVIEW if new > old else Severity.INFO,
                f"{name} {'went up' if new > old else 'went down'} from {msg.money(old)} to "
                f"{msg.money(new)} on {msg.day(changed.date, ctx.as_of)}.",
                [changed.id],
            )
        ]
    if len(amounts) < 3:
        return []
    usual = _median_money(amounts[:-1])
    latest = amounts[-1]
    last = kept[-1]
    when = msg.day(last.date, ctx.as_of)
    if model.fixed:
        if abs(latest - usual) <= usual * FIXED_PRICE_BAND:
            return []
        higher = latest > usual
        return [
            Flag(
                FlagKind.AMOUNT_CHANGED,
                Severity.REVIEW if higher else Severity.INFO,
                f"{name} is usually {msg.money(usual)}, but the latest charge on {when} was "
                f"{msg.money(latest)}."
                + (" Prices sometimes go up, but it's worth checking." if higher else ""),
                [last.id],
            )
        ]
    if latest >= usual * SPIKE_RATIO and latest - usual >= SPIKE_MIN_DIFFERENCE:
        ratio = (latest / usual).quantize(Decimal("0.1"), ROUND_HALF_UP)
        return [
            Flag(
                FlagKind.AMOUNT_CHANGED,
                Severity.REVIEW,
                f"Your {name} bill is usually around {msg.money(usual)}, but the latest one on "
                f"{when} was {msg.money(latest)}. That's about {ratio} times the usual amount.",
                [last.id],
            )
        ]
    if latest * SPIKE_RATIO <= usual and usual - latest >= SPIKE_MIN_DIFFERENCE:
        return [
            Flag(
                FlagKind.AMOUNT_CHANGED,
                Severity.INFO,
                f"The latest {name} charge was {msg.money(latest)}, lower than the usual "
                f"{msg.money(usual)}.",
                [last.id],
            )
        ]
    return []


def _possible_bill(
    series: _Series,
    kept: list[Transaction],
    dupes: list[tuple[Transaction, Transaction]],
    ctx: _Context,
) -> Bill | None:
    """Too few charges, or too little history, to call something a bill. If it
    looks like one anyway, ask the user rather than assume."""
    tx = kept[-1]
    age = (ctx.as_of - tx.date).days
    text = f"{tx.merchant_name or ''} {tx.name}".upper()
    hinted = (
        series.payee.subscription or tx.category in BILL_CATEGORIES or bool(BILL_WORDS.search(text))
    )
    next_due = None
    # A subscription service charged once, most of a year ago, is most likely on a
    # yearly plan and about to renew. That is exactly the charge people forget.
    yearly_hint = bool(YEARLY_WORDS.search(text)) or (series.payee.subscription and age >= 300)
    if len(kept) == 1 and yearly_hint and age <= SEEN_ONCE_YEARLY_DAYS:
        frequency = Frequency.ANNUAL
        next_due = tx.date + relativedelta(years=1)
        message = (
            f"I've only seen one charge from {series.payee.display}: {msg.money(tx.amount)} on "
            f"{msg.day(tx.date, ctx.as_of)}. It looks like a yearly renewal, so the next one "
            f"may come around {msg.day(next_due, ctx.as_of)}. Is this a yearly bill?"
        )
    elif hinted and age <= SEEN_ONCE_RECENT_DAYS:
        frequency = Frequency.UNKNOWN
        if len(kept) == 1:
            message = (
                f"I've only seen one charge from {series.payee.display}: "
                f"{msg.money(tx.amount)} on {msg.day(tx.date, ctx.as_of)}. It could be a "
                f"regular bill, but I need to see it again to be sure."
            )
        else:
            message = (
                f"I've seen {len(kept)} charges from {series.payee.display} so far, most "
                f"recently {msg.money(tx.amount)} on {msg.day(tx.date, ctx.as_of)}. It could be "
                f"a regular bill, but I need more history to be sure."
            )
    else:
        return None

    bill = Bill(
        id=_bill_id(series),
        payee=series.payee.display,
        payee_key=series.key,
        frequency=frequency,
        status=BillStatus.POSSIBLE,
        typical_amount=_median_money([t.amount for t in kept]),
        min_amount=min(t.amount for t in kept),
        max_amount=max(t.amount for t in kept),
        last_amount=tx.amount,
        last_date=tx.date,
        next_due=next_due,
        next_due_earliest=None,
        next_due_latest=None,
        confidence=0.3,
        occurrences=len(kept),
        account_ids=sorted({t.account_id for t in series.txs}),
        transaction_ids=[t.id for t in series.txs],
        category=tx.category,
        reasons=[f"Seen {msg.times(len(kept))}, most recently on {msg.day(tx.date, ctx.as_of)}."],
    )
    bill.flags.append(Flag(FlagKind.SEEN_ONCE, Severity.REVIEW, message, [tx.id]))
    bill.flags += _duplicate_flags(series, dupes, ctx)
    return bill


def _reasons(
    kept: list[Transaction],
    frequency: Frequency,
    intervals: list[int],
    model: _AmountModel,
    gaps: int,
    ctx: _Context,
) -> list[str]:
    n = len(kept)
    since = msg.month(kept[0].date)
    if frequency is Frequency.IRREGULAR:
        rhythm = f"Charged {msg.times(n)} since {since}, {_week_range(intervals)} apart."
    else:
        rhythm = f"Charged {msg.times(n)} since {since}, {msg.FREQUENCY_WORDS[frequency]}."
    reasons = [rhythm]
    amounts = [t.amount for t in kept]
    low, high = min(amounts), max(amounts)
    if model.price_change_at is not None:
        old = _median_money(amounts[: model.price_change_at])
        changed = kept[model.price_change_at].date
        reasons.append(
            f"Now {msg.money(model.typical)}. It was {msg.money(old)} until "
            f"{msg.day(changed, ctx.as_of)}."
        )
    elif low == high:
        reasons.append(f"Always {msg.money(model.typical)}.")
    else:
        reasons.append(
            f"Usually around {msg.money(model.typical)} (between {msg.money(low)} and "
            f"{msg.money(high)})."
        )
    if gaps:
        reasons.append("One expected charge was skipped along the way.")
    return reasons


# --- unreadable transactions -----------------------------------------------


def _attach_unreadable(
    unreadable: list[UnreadableTransaction], bills: list[Bill], ctx: _Context
) -> list[Flag]:
    global_flags: list[Flag] = []
    for u in unreadable:
        payee = normalize_payee(u.name) if u.name else None
        name = payee.display if payee else "an unnamed payee"
        if u.problem == "amount":
            flag = Flag(
                FlagKind.UNREADABLE_TRANSACTION,
                Severity.REVIEW,
                f"There's a transaction from {name} where I can't read the amount, so I've left "
                f"it out. You may want to check it with your bank.",
                [u.id],
            )
        else:
            assert u.amount is not None
            if u.amount <= 0:
                continue  # money in; can never be a bill
            flag = Flag(
                FlagKind.UNREADABLE_TRANSACTION,
                Severity.REVIEW,
                f"I couldn't read the date on a {msg.money(u.amount)} charge from {name}, so I've "
                f"left it out of my counts.",
                [u.id],
            )
        bill = _matching_bill(payee, u.amount, bills)
        if bill is None:
            global_flags.append(flag)
            continue
        missing = [f for f in bill.flags if f.kind is FlagKind.EXPECTED_CHARGE_MISSING]
        if (
            missing
            and missing[0].severity is Severity.REVIEW
            and u.amount is not None
            and abs(u.amount - bill.typical_amount) <= bill.typical_amount / 2
            and bill.next_due is not None
        ):
            # The "missing" charge is probably this one. Say so once, not twice.
            bill.flags.remove(missing[0])
            flag.message += (
                f" It may be the payment I was expecting around "
                f"{msg.day(bill.next_due, ctx.as_of)}."
            )
        bill.flags.append(flag)
    return global_flags


def _matching_bill(payee: Payee | None, amount: Decimal | None, bills: list[Bill]) -> Bill | None:
    if payee is None:
        return None
    candidates = [
        b for b in bills if b.payee_key == payee.key and b.status is not BillStatus.STOPPED
    ]
    if not candidates:
        return None
    if amount is None:
        return candidates[0]
    return min(candidates, key=lambda b: abs(b.typical_amount - amount))


# --- helpers ---------------------------------------------------------------


def _median_money(amounts: list[Decimal]) -> Decimal:
    return Decimal(median(amounts)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def _share_within(amounts: list[Decimal], center: Decimal, fraction: Decimal) -> float:
    limit = center * fraction
    return sum(1 for a in amounts if abs(a - center) <= limit) / len(amounts)


def _week_range(intervals: list[int]) -> str:
    low, high = round(min(intervals) / 7), round(max(intervals) / 7)
    return f"about {low} weeks" if low == high else f"usually {low} to {high} weeks"


def _category(txs: list[Transaction]) -> str | None:
    cats = [t.category for t in txs if t.category]
    # Most common, ties broken alphabetically so the result never depends on set order.
    return min(set(cats), key=lambda c: (-cats.count(c), c)) if cats else None


def _bill_id(series: _Series) -> str:
    return hashlib.sha1(f"{series.key}#{series.ordinal}".encode()).hexdigest()[:12]
