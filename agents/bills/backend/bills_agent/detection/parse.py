"""Turn raw Plaid-shaped transaction dicts into typed transactions.

Anything we cannot read with certainty is kept aside as ``UnreadableTransaction``
so the detector can tell the user about it instead of silently dropping it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .models import Transaction, UnreadableTransaction


def parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def parse_amount(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        # str() first so floats like 15.49 don't become 15.4900000000000002131...
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite():
        return None
    return amount.quantize(Decimal("0.01"))


def _category(raw: Mapping[str, Any]) -> str | None:
    pfc = raw.get("personal_finance_category")
    if isinstance(pfc, Mapping):
        primary = pfc.get("primary")
        return str(primary) if primary else None
    return None


def parse_transactions(
    raw_transactions: Iterable[Mapping[str, Any]],
) -> tuple[list[Transaction], list[UnreadableTransaction]]:
    good: list[Transaction] = []
    bad: list[UnreadableTransaction] = []
    for raw in raw_transactions:
        tx_id = str(raw.get("transaction_id") or "")
        name = str(raw.get("name") or raw.get("merchant_name") or "").strip()
        amount = parse_amount(raw.get("amount"))
        tx_date = parse_date(raw.get("date"))
        raw_date = raw.get("date")
        if amount is None:
            bad.append(UnreadableTransaction(tx_id, name, None, _as_text(raw_date), "amount"))
            continue
        if tx_date is None:
            bad.append(UnreadableTransaction(tx_id, name, amount, _as_text(raw_date), "date"))
            continue
        good.append(
            Transaction(
                id=tx_id,
                account_id=str(raw.get("account_id") or ""),
                amount=amount,
                date=tx_date,
                name=name,
                merchant_name=(raw.get("merchant_name") or None),
                category=_category(raw),
                pending=bool(raw.get("pending", False)),
            )
        )
    return good, bad


def _as_text(value: Any) -> str | None:
    return None if value is None else str(value)
