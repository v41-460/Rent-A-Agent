"""HTTP endpoints for the Bills agent.

``router`` is the shared agent interface (/manifest, /health, /run).
``extra_router`` holds the endpoints the Bills page needs for bank sign-in. The platform
serves them at /api/agents/bills/x/... only to logged-in users who rented Bills, and tells
us who the user is in the X-Rent-User-Id header. Plaid access tokens never appear in any
response: the browser only sees a short-lived link token and sends back a public token.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from rent_agent_interface import (
    ItemsBlock,
    NoticeBlock,
    RunRequest,
    RunResponse,
    TextBlock,
    make_agent_router,
)
from sqlalchemy.orm import Session

from . import audit, service
from .bank import BankError, BankProvider, PlaidProvider
from .config import Settings, get_settings
from .crypto import TokenVault
from .db import Database
from .detection.messages import FREQUENCY_WORDS

MANIFEST = Path(__file__).resolve().parents[2] / "manifest.json"


@dataclass
class _State:
    settings: Settings
    db: Database
    bank: BankProvider | None
    today: Callable[[], date]
    _vault: TokenVault | None = None

    @property
    def vault(self) -> TokenVault:
        if self._vault is None:
            if not self.settings.bills_token_encryption_key:
                raise BankError("not_configured")
            self._vault = TokenVault(self.settings.bills_token_encryption_key)
        return self._vault

    def get_bank(self) -> BankProvider:
        if self.bank is None:
            self.bank = PlaidProvider(self.settings)
        return self.bank


_state: _State | None = None


def configure(
    settings: Settings | None = None,
    bank: BankProvider | None = None,
    today: Callable[[], date] = date.today,
) -> None:
    """Set up (or, in tests, replace) settings, storage and the bank. Called lazily."""
    global _state
    settings = settings or get_settings()
    _state = _State(settings=settings, db=Database(settings.database_url), bank=bank, today=today)


def state() -> _State:
    if _state is None:
        configure()
    assert _state is not None
    return _state


def get_session() -> Iterator[Session]:
    yield from state().db.session()


def rent_user(x_rent_user_id: str | None = Header(default=None)) -> str:
    if not x_rent_user_id:
        raise HTTPException(401, detail={"code": "not_logged_in", "message": "Please log in."})
    return x_rent_user_id


# --- the shared interface ---------------------------------------------------------------

router = make_agent_router(MANIFEST)


def _bill_item(bill: dict[str, Any]) -> dict[str, str]:
    how_often = FREQUENCY_WORDS.get(bill["frequency"], "now and then")
    due = bill.get("next_due")
    due_text = f"next due {date.fromisoformat(due):%b} {date.fromisoformat(due).day}" if due else ""
    return {
        "title": bill["payee"],
        "subtitle": ", ".join(x for x in (how_often.capitalize(), due_text) if x),
        "value": f"${float(bill['typical_amount']):,.2f}",
    }


@router.post("/run", response_model=RunResponse)
def run(req: RunRequest, session: Session = Depends(get_session)) -> RunResponse:
    latest = service.latest_run(session, req.user.id)
    if latest is None:
        text = "Open the Bills page and connect your bank (or the practice bank) to see your bills."
        return RunResponse(
            status="needs_input", message=text, blocks=[NoticeBlock(level="info", text=text)]
        )
    bills = [b for b in latest.result["bills"] if b["status"] != "stopped"]
    return RunResponse(
        status="ok",
        message=f"Found {len(bills)} regular bills.",
        blocks=[
            TextBlock(text=f"Found {len(bills)} regular bills."),
            ItemsBlock(items=[_bill_item(b) for b in bills], empty_text="No regular bills found."),
        ],
    )


# --- endpoints for the Bills page -------------------------------------------------------

extra_router = APIRouter()


class LinkTokenRequest(BaseModel):
    reconnect: bool = False


class ExchangeRequest(BaseModel):
    public_token: str
    institution: dict[str, Any] | None = None


class LinkEvent(BaseModel):
    # What happened in Plaid Link, for the audit log. No credentials ever come here.
    event: Literal["opened", "exit", "error"]
    error_code: str | None = None
    error_type: str | None = None
    link_status: str | None = None
    institution_name: str | None = None


def bank_error_response(exc: BankError) -> JSONResponse:
    status = 503 if exc.code in ("bank_unavailable", "busy", "not_configured") else 409
    return JSONResponse(
        status_code=status, content={"detail": {"code": exc.code, "message": exc.message}}
    )


@extra_router.post("/link/token")
def link_token(
    body: LinkTokenRequest,
    user_id: str = Depends(rent_user),
    session: Session = Depends(get_session),
) -> Any:
    st = state()
    try:
        access_token = None
        if body.reconnect:
            for item in service.items_for(session, user_id):
                if item.status == "reconnect_needed":
                    access_token = st.vault.open(item.access_token_encrypted)
                    break
        return st.get_bank().create_link_token(user_id, access_token)
    except BankError as exc:
        return bank_error_response(exc)


@extra_router.post("/link/exchange")
def exchange(
    body: ExchangeRequest,
    user_id: str = Depends(rent_user),
    session: Session = Depends(get_session),
) -> Any:
    st = state()
    try:
        item = service.connect_bank(
            session, user_id, st.get_bank(), st.vault, body.public_token, body.institution
        )
    except BankError as exc:
        return bank_error_response(exc)
    return {"connected": True, "institution_name": item.institution_name}


@extra_router.post("/link/reconnected")
def reconnected(
    user_id: str = Depends(rent_user), session: Session = Depends(get_session)
) -> dict[str, bool]:
    """Called after the person signs in again through Plaid Link's update mode."""
    for item in service.items_for(session, user_id):
        if item.status == "reconnect_needed":
            item.status = "ok"
            audit.record(session, user_id, "user", "bank_reconnected", item.institution_name)
    session.commit()
    return {"ok": True}


@extra_router.post("/link/event")
def link_event(
    body: LinkEvent, user_id: str = Depends(rent_user), session: Session = Depends(get_session)
) -> dict[str, bool]:
    audit.record(
        session,
        user_id,
        "user",
        f"link_{body.event}",
        body.institution_name,
        error_code=body.error_code,
        error_type=body.error_type,
        link_status=body.link_status,
    )
    session.commit()
    return {"ok": True}


@extra_router.get("/connection")
def connection(
    user_id: str = Depends(rent_user), session: Session = Depends(get_session)
) -> dict[str, Any]:
    items = service.items_for(session, user_id)
    st = state()
    return {
        "connected": bool(items),
        "bank_available": st.settings.plaid_configured,
        "banks": [
            {
                "name": i.institution_name,
                "status": i.status,
                "last_synced_at": i.last_synced_at.isoformat() if i.last_synced_at else None,
            }
            for i in items
        ],
    }


@extra_router.post("/sample")
def sample(user_id: str = Depends(rent_user), session: Session = Depends(get_session)) -> Any:
    """Load a practice household so Bills can be tried without a bank."""
    from bills_fixtures import scenarios
    from bills_fixtures.builder import ACCOUNT_NAMES

    household = scenarios.typical_household()
    today = state().today()
    try:
        service.load_sample(
            session,
            user_id,
            household.transactions,
            ACCOUNT_NAMES,
            shift_days=(today - household.as_of).days,
        )
    except BankError as exc:
        return bank_error_response(exc)
    run = service.run_detection(session, user_id, today)
    return {"status": "ready", "bill_count": len(run.result["bills"])}


@extra_router.post("/disconnect")
def disconnect(
    user_id: str = Depends(rent_user), session: Session = Depends(get_session)
) -> dict[str, bool]:
    service.disconnect_all(session, user_id)
    return {"ok": True}


@extra_router.post("/sync")
def sync(user_id: str = Depends(rent_user), session: Session = Depends(get_session)) -> Any:
    """Fetch new transactions, then look for bills again."""
    st = state()
    try:
        status = service.sync_all(session, user_id, st.get_bank, lambda: st.vault)
    except BankError as exc:
        return bank_error_response(exc)
    if status == "not_connected":
        return {"status": status}
    if status == "still_loading":
        return {"status": status, "message": BankError("still_loading").message}
    run = service.run_detection(session, user_id, st.today())
    response: dict[str, Any] = {
        "status": "ready" if status == "nothing_new" else status,
        "bill_count": len(run.result["bills"]),
    }
    if status == "reconnect_needed":
        response["message"] = BankError("reconnect_needed").message
    return response


@extra_router.get("/bills")
def bills(user_id: str = Depends(rent_user), session: Session = Depends(get_session)) -> Any:
    run = service.latest_run(session, user_id)
    if run is None:
        return {"status": "not_run"}
    return {"status": "ready", "transaction_count": run.transaction_count, **run.result}


__all__ = ["router", "extra_router", "configure"]
