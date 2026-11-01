"""What the Bills agent does, independent of HTTP. Every function is scoped to one user."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import audit
from .bank import BankError, BankProvider
from .crypto import TokenVault
from .db import Account, DetectionRun, PlaidItem, StoredTransaction, utcnow
from .detection import Bill, BillStatus, DetectionResult, Flag, Severity, detect_bills

DUE_SOON_DAYS = 7
SAMPLE_STATUS = "sample"
SAMPLE_NAME = "Practice bank (sample data)"
# Plaid asks us to restart from the last good cursor when data changes mid-sync.
_MUTATION_RESTARTS = 3


def items_for(session: Session, user_id: str) -> list[PlaidItem]:
    return list(session.scalars(select(PlaidItem).where(PlaidItem.user_id == user_id)))


def connect_bank(
    session: Session,
    user_id: str,
    bank: BankProvider,
    vault: TokenVault,
    public_token: str,
    institution: dict[str, Any] | None,
) -> PlaidItem:
    access_token, item_id = bank.exchange_public_token(public_token)
    institution = institution or {}
    item = session.get(PlaidItem, item_id)
    if item is not None and item.user_id != user_id:
        # Plaid item ids are unique per login; this would mean a token mix-up. Refuse.
        raise BankError("unknown")
    item = item or PlaidItem(item_id=item_id, user_id=user_id)
    item.access_token_encrypted = vault.seal(access_token)
    item.institution_id = institution.get("institution_id") or institution.get("id")
    item.institution_name = institution.get("name") or "your bank"
    item.status = "ok"
    session.add(item)
    accounts = bank.get_accounts(access_token)
    for raw in accounts:
        _upsert_account(session, user_id, item_id, raw)
    _drop_sample(session, user_id)  # A real bank replaces practice data.
    audit.record(
        session,
        user_id,
        "user",
        "bank_connected",
        item.institution_name,
        item_id=item_id,
        accounts=len(accounts),
    )
    session.commit()
    return item


def _upsert_account(session: Session, user_id: str, item_id: str, raw: dict[str, Any]) -> None:
    account = session.scalars(
        select(Account).where(Account.user_id == user_id, Account.account_id == raw["account_id"])
    ).first() or Account(account_id=raw["account_id"], user_id=user_id)
    account.item_id = item_id
    account.name = raw.get("official_name") or raw.get("name") or "Account"
    account.mask = raw.get("mask")
    account.type = raw.get("type")
    account.subtype = raw.get("subtype")
    session.add(account)


def _drop_sample(session: Session, user_id: str) -> None:
    sample = [i.item_id for i in items_for(session, user_id) if i.status == SAMPLE_STATUS]
    if not sample:
        return
    session.execute(delete(StoredTransaction).where(StoredTransaction.item_id.in_(sample)))
    session.execute(delete(Account).where(Account.item_id.in_(sample)))
    session.execute(delete(PlaidItem).where(PlaidItem.item_id.in_(sample)))
    session.execute(delete(DetectionRun).where(DetectionRun.user_id == user_id))


def load_sample(
    session: Session,
    user_id: str,
    transactions: list[dict[str, Any]],
    accounts: dict[str, str],
    shift_days: int,
) -> None:
    """Practice data so people (and tests) can try Bills without a bank. Never mixed with a
    real bank: refused if one is connected."""
    if any(i.status != SAMPLE_STATUS for i in items_for(session, user_id)):
        raise BankError("already_connected")
    _drop_sample(session, user_id)
    item_id = f"sample-{user_id}"
    session.add(
        PlaidItem(
            item_id=item_id,
            user_id=user_id,
            access_token_encrypted="",
            institution_name=SAMPLE_NAME,
            status=SAMPLE_STATUS,
        )
    )
    session.flush()
    for account_id, label in accounts.items():
        name, _, mask = label.partition(" (...")
        _upsert_account(
            session,
            user_id,
            item_id,
            {"account_id": account_id, "name": name, "mask": mask.rstrip(")") or None},
        )
    for tx in transactions:
        raw = dict(tx)
        for key in ("date", "authorized_date"):
            if raw.get(key):
                raw[key] = (date.fromisoformat(raw[key]) + timedelta(days=shift_days)).isoformat()
        session.add(
            StoredTransaction(
                transaction_id=raw["transaction_id"],
                item_id=item_id,
                user_id=user_id,
                account_id=raw["account_id"],
                raw=raw,
            )
        )
    audit.record(session, user_id, "user", "sample_loaded", SAMPLE_NAME, count=len(transactions))
    session.commit()


def disconnect_all(session: Session, user_id: str) -> None:
    """Forget every bank connection and everything learned from it, for this user only."""
    ids = [i.item_id for i in items_for(session, user_id)]
    session.execute(delete(StoredTransaction).where(StoredTransaction.user_id == user_id))
    session.execute(delete(Account).where(Account.user_id == user_id))
    session.execute(delete(PlaidItem).where(PlaidItem.user_id == user_id))
    session.execute(delete(DetectionRun).where(DetectionRun.user_id == user_id))
    audit.record(session, user_id, "user", "bank_disconnected", None, items=len(ids))
    session.commit()


def sync_all(
    session: Session,
    user_id: str,
    get_bank: Callable[[], BankProvider],
    get_vault: Callable[[], TokenVault],
) -> str:
    """Pull new transactions from every bank this user connected.

    Returns "ready", "still_loading", "reconnect_needed", "not_connected", or
    "nothing_new" when only practice data is loaded. Bank outages raise BankError.
    """
    items = items_for(session, user_id)
    if not items:
        return "not_connected"
    items = [i for i in items if i.status != SAMPLE_STATUS]
    if not items:
        return "nothing_new"
    bank, vault = get_bank(), get_vault()
    outcome = "ready"
    for item in items:
        if item.status == "reconnect_needed":
            outcome = "reconnect_needed"
            continue
        try:
            status = _sync_item(session, bank, vault, item)
        except BankError as exc:
            if exc.code != "reconnect_needed":
                raise
            item.status = "reconnect_needed"
            audit.record(
                session,
                user_id,
                "system",
                "reconnect_needed",
                item.institution_name,
                plaid_code=exc.plaid_code,
            )
            session.commit()
            outcome = "reconnect_needed"
            continue
        if status == "still_loading" and outcome == "ready":
            outcome = "still_loading"
    return outcome


def _sync_item(session: Session, bank: BankProvider, vault: TokenVault, item: PlaidItem) -> str:
    access_token = vault.open(item.access_token_encrypted)
    start_cursor = item.sync_cursor
    for _ in range(_MUTATION_RESTARTS):
        cursor = start_cursor
        added: dict[str, dict[str, Any]] = {}
        removed: set[str] = set()
        try:
            while True:
                page = bank.sync_transactions(access_token, cursor)
                for tx in page.added + page.modified:
                    added[tx["transaction_id"]] = tx
                    removed.discard(tx["transaction_id"])
                for tx_id in page.removed:
                    added.pop(tx_id, None)
                    removed.add(tx_id)
                cursor = page.next_cursor
                if not page.has_more:
                    break
        except BankError as exc:
            if exc.plaid_code == "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION":
                continue
            raise
        break
    else:
        raise BankError("busy")

    for tx_id, raw in added.items():
        row = session.scalars(
            select(StoredTransaction).where(
                StoredTransaction.user_id == item.user_id,
                StoredTransaction.transaction_id == tx_id,
            )
        ).first() or StoredTransaction(transaction_id=tx_id, user_id=item.user_id)
        row.item_id = item.item_id
        row.account_id = raw.get("account_id", "")
        row.raw = raw
        row.updated_at = utcnow()
        session.add(row)
    if removed:
        session.execute(
            delete(StoredTransaction).where(
                StoredTransaction.user_id == item.user_id,
                StoredTransaction.transaction_id.in_(removed),
            )
        )
    item.sync_cursor = cursor
    item.last_synced_at = utcnow()
    audit.record(
        session,
        item.user_id,
        "system",
        "transactions_synced",
        item.institution_name,
        added_or_changed=len(added),
        removed=len(removed),
        plaid_status=page.update_status,
    )
    session.commit()

    if page.update_status == "NOT_READY" and not added and start_cursor is None:
        return "still_loading"
    return "ready"


def run_detection(session: Session, user_id: str, as_of: date) -> DetectionRun:
    raws = [
        row.raw
        for row in session.scalars(
            select(StoredTransaction).where(StoredTransaction.user_id == user_id)
        )
    ]
    accounts = {
        a.account_id: a.label
        for a in session.scalars(select(Account).where(Account.user_id == user_id))
    }
    result = detect_bills(raws, as_of, accounts)
    run = DetectionRun(
        user_id=user_id,
        as_of=as_of.isoformat(),
        transaction_count=len(raws),
        result=serialize_result(result),
    )
    session.add(run)
    _audit_detection(session, user_id, result)
    session.commit()
    return run


def _audit_detection(session: Session, user_id: str, result: DetectionResult) -> None:
    for bill in result.bills:
        audit.record(
            session,
            user_id,
            "agent",
            "bill_detected",
            bill.payee,
            bill_id=bill.id,
            status=bill.status.value,
            frequency=bill.frequency.value,
            typical_amount=str(bill.typical_amount),
            confidence=bill.confidence,
            next_due=bill.next_due.isoformat() if bill.next_due else None,
            transaction_ids=bill.transaction_ids,
            reasons=bill.reasons,
        )
        for flag in bill.flags:
            audit.record(
                session,
                user_id,
                "agent",
                "flag_raised",
                bill.payee,
                bill_id=bill.id,
                **_flag_dict(flag),
            )
    for flag in result.flags:
        audit.record(session, user_id, "agent", "flag_raised", None, **_flag_dict(flag))


def latest_run(session: Session, user_id: str) -> DetectionRun | None:
    return session.scalars(
        select(DetectionRun)
        .where(DetectionRun.user_id == user_id)
        .order_by(DetectionRun.id.desc())
        .limit(1)
    ).first()


# --- shaping results ---------------------------------------------------------------


def bucket(bill: Bill, as_of: date) -> str:
    """Which list a bill belongs in (or "stopped", shown separately)."""
    if bill.status is BillStatus.STOPPED:
        return "stopped"
    if bill.status is BillStatus.POSSIBLE or bill.needs_review:
        return "needs_attention"
    if bill.next_due is not None and bill.next_due <= as_of + timedelta(days=DUE_SOON_DAYS):
        return "due_soon"
    return "upcoming"


def serialize_result(result: DetectionResult) -> dict[str, Any]:
    return {
        "as_of": result.as_of.isoformat(),
        "history_days": result.history_days,
        "bills": [{**_bill_dict(b), "bucket": bucket(b, result.as_of)} for b in result.bills],
        "flags": [_flag_dict(f) for f in result.flags if f.severity is Severity.REVIEW],
    }


def _bill_dict(bill: Bill) -> dict[str, Any]:
    return {
        "id": bill.id,
        "payee": bill.payee,
        "frequency": bill.frequency.value,
        "status": bill.status.value,
        "typical_amount": _money(bill.typical_amount),
        "min_amount": _money(bill.min_amount),
        "max_amount": _money(bill.max_amount),
        "last_amount": _money(bill.last_amount),
        "last_date": bill.last_date.isoformat(),
        "next_due": _iso(bill.next_due),
        "next_due_earliest": _iso(bill.next_due_earliest),
        "next_due_latest": _iso(bill.next_due_latest),
        "confidence": bill.confidence,
        "occurrences": bill.occurrences,
        "account_count": len(bill.account_ids),
        "category": bill.category,
        "reasons": bill.reasons,
        "flags": [_flag_dict(f) for f in bill.flags],
    }


def _flag_dict(flag: Flag) -> dict[str, Any]:
    return {"kind": flag.kind.value, "severity": flag.severity.value, "message": flag.message}


def _money(amount: Decimal) -> str:
    # Strings, not floats, so no rounding happens on the way to the screen.
    return f"{amount:.2f}"


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None
