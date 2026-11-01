"""Runs the detector against every edge-case scenario. A failure here is a bug."""

from __future__ import annotations

import random
from decimal import Decimal

import pytest

from bills_agent.detection import DetectionResult, Severity, detect_bills
from bills_fixtures import scenarios
from bills_fixtures.builder import ACCOUNT_NAMES


def _review(flags) -> set[str]:
    return {f.kind.value for f in flags if f.severity is Severity.REVIEW}


def _check(s: scenarios.Scenario, result: DetectionResult) -> list[str]:
    problems: list[str] = []
    remaining = list(result.bills)
    for exp in s.bills:
        same_name = [b for b in remaining if b.payee == exp.payee]
        if exp.typical_amount and len(same_name) > 1:
            same_name = [b for b in same_name if b.typical_amount == Decimal(exp.typical_amount)]
        if not same_name:
            problems.append(f"missing bill: {exp.payee}")
            continue
        bill = same_name[0]
        remaining.remove(bill)
        where = f"{exp.payee} ({bill.typical_amount})"
        checks = {
            "frequency": (bill.frequency.value, exp.frequency),
            "status": (bill.status.value, exp.status),
        }
        if exp.typical_amount is not None:
            checks["typical_amount"] = (bill.typical_amount, Decimal(exp.typical_amount))
        if exp.next_due is not None:
            checks["next_due"] = (bill.next_due and bill.next_due.isoformat(), exp.next_due)
        if exp.occurrences is not None:
            checks["occurrences"] = (bill.occurrences, exp.occurrences)
        checks["review flags"] = (_review(bill.flags), exp.review_flags)
        for label, (got, want) in checks.items():
            if got != want:
                problems.append(f"{where}: {label} is {got!r}, expected {want!r}")
        info = {f.kind.value for f in bill.flags if f.severity is Severity.INFO}
        if not exp.info_flags <= info:
            problems.append(f"{where}: info flags {info!r} missing {exp.info_flags - info!r}")
        if exp.min_confidence is not None and bill.confidence < exp.min_confidence:
            problems.append(f"{where}: confidence {bill.confidence} < {exp.min_confidence}")
        if exp.max_confidence is not None and bill.confidence > exp.max_confidence:
            problems.append(f"{where}: confidence {bill.confidence} > {exp.max_confidence}")
    for bill in remaining:
        problems.append(
            f"unexpected bill: {bill.payee} {bill.typical_amount} {bill.frequency.value}"
        )
    for name in s.not_bills:
        if any(b.payee == name for b in result.bills):
            problems.append(f"{name} must not be a bill")
    if _review(result.flags) != s.global_flags:
        problems.append(
            f"global review flags {_review(result.flags)!r}, expected {s.global_flags!r}"
        )
    return problems


def _describe(result: DetectionResult) -> str:
    lines = []
    for b in result.bills:
        lines.append(
            f"  {b.payee}: {b.frequency.value} {b.status.value} {b.typical_amount} "
            f"next={b.next_due} n={b.occurrences} conf={b.confidence}"
        )
        lines += [f"      [{f.severity.value}] {f.kind.value}: {f.message}" for f in b.flags]
    lines += [f"  [global {f.severity.value}] {f.kind.value}: {f.message}" for f in result.flags]
    return "\n".join(lines)


@pytest.mark.parametrize("make", scenarios.ALL, ids=lambda f: f.__name__)
def test_scenario(make):
    s = make()
    result = detect_bills(s.transactions, s.as_of, ACCOUNT_NAMES)
    problems = _check(s, result)
    assert not problems, "\n".join(problems) + "\n\nDetected:\n" + _describe(result)


@pytest.mark.parametrize("make", scenarios.ALL, ids=lambda f: f.__name__)
def test_input_order_does_not_matter(make):
    s = make()
    shuffled = list(s.transactions)
    random.Random(42).shuffle(shuffled)
    a = detect_bills(s.transactions, s.as_of, ACCOUNT_NAMES)
    b = detect_bills(shuffled, s.as_of, ACCOUNT_NAMES)
    assert _describe(a) == _describe(b)
    assert [x.id for x in a.bills] == [x.id for x in b.bills]


def test_pending_transactions_are_ignored():
    s = scenarios.double_charge()
    for tx in s.transactions:
        if tx["name"] == "NETFLIX.COM":
            tx["pending"] = True
    result = detect_bills(s.transactions, s.as_of)
    assert not [b for b in result.bills if b.payee == "Netflix"]


def test_every_flag_message_is_plain_text():
    for make in scenarios.ALL:
        s = make()
        result = detect_bills(s.transactions, s.as_of, ACCOUNT_NAMES)
        flags = result.flags + [f for b in result.bills for f in b.flags]
        for f in flags:
            assert f.message.strip(), f
            assert f.message.endswith((".", "?")), f.message
            # No internal ids or raw enum names leaking into what the user reads.
            assert "acc_" not in f.message and "tx_" not in f.message and "_" not in f.message
