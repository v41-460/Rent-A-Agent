"""Talking to the bank, through Plaid (sandbox only).

Everything Plaid-specific lives here behind ``BankProvider`` so the rest of the
app, and the tests, never touch the Plaid SDK directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol

import plaid
from plaid.api import plaid_api
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.link_token_transactions import LinkTokenTransactions
from plaid.model.products import Products
from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest
from plaid.model.sandbox_public_token_create_request_options import (
    SandboxPublicTokenCreateRequestOptions,
)
from plaid.model.sandbox_public_token_create_request_options_transactions import (
    SandboxPublicTokenCreateRequestOptionsTransactions,
)
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.transactions_sync_request_options import TransactionsSyncRequestOptions

from .config import Settings


class BankError(Exception):
    """A bank or Plaid problem, translated into something we can explain calmly.

    ``code`` is one of the keys of ``FRIENDLY_MESSAGES``.
    """

    def __init__(self, code: str, plaid_code: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.plaid_code = plaid_code

    @property
    def message(self) -> str:
        return FRIENDLY_MESSAGES.get(self.code, FRIENDLY_MESSAGES["unknown"])


FRIENDLY_MESSAGES = {
    "reconnect_needed": "Your bank needs you to sign in again before we can see new "
    "transactions. Nothing is wrong with your account.",
    "still_loading": "Your bank is still sending your transactions. This can take a minute "
    "the first time.",
    "bank_unavailable": "Your bank isn't responding right now. This is usually temporary. "
    "Please try again in a little while.",
    "link_expired": "That took a little too long and the connection timed out. Let's try again.",
    "busy": "We're a bit busy right now. Please try again in a minute.",
    "not_configured": "The bank connection hasn't been set up on this server yet. You can "
    "still try Bills with the practice bank.",
    "already_connected": "You already have a bank connected, so practice data isn't needed.",
    "unknown": "Something didn't work, but nothing has changed in your bank account. "
    "Let's try again.",
}

# Plaid error_code -> our code. Anything unlisted becomes "unknown".
_PLAID_CODES = {
    "ITEM_LOGIN_REQUIRED": "reconnect_needed",
    "PENDING_EXPIRATION": "reconnect_needed",
    "ACCESS_NOT_GRANTED": "reconnect_needed",
    "PRODUCT_NOT_READY": "still_loading",
    "INSTITUTION_DOWN": "bank_unavailable",
    "INSTITUTION_NOT_RESPONDING": "bank_unavailable",
    "INSTITUTION_NOT_AVAILABLE": "bank_unavailable",
    "INSTITUTION_NO_LONGER_SUPPORTED": "bank_unavailable",
    "INVALID_LINK_TOKEN": "link_expired",
    "INVALID_PUBLIC_TOKEN": "link_expired",
    "RATE_LIMIT_EXCEEDED": "busy",
    "TRANSACTIONS_LIMIT": "busy",
}


@dataclass
class SyncPage:
    added: list[dict[str, Any]] = field(default_factory=list)
    modified: list[dict[str, Any]] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    next_cursor: str = ""
    has_more: bool = False
    # Plaid's transactions_update_status, e.g. "NOT_READY", "HISTORICAL_UPDATE_COMPLETE".
    update_status: str = ""


class BankProvider(Protocol):
    def create_link_token(
        self, user_id: str, access_token: str | None = None
    ) -> dict[str, str]: ...

    def exchange_public_token(self, public_token: str) -> tuple[str, str]: ...

    def get_accounts(self, access_token: str) -> list[dict[str, Any]]: ...

    def sync_transactions(self, access_token: str, cursor: str | None) -> SyncPage: ...


class PlaidProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.plaid_configured:
            raise BankError("not_configured")
        configuration = plaid.Configuration(
            host=plaid.Environment.Sandbox,
            api_key={"clientId": settings.plaid_client_id, "secret": settings.plaid_secret},
        )
        self._client = plaid_api.PlaidApi(plaid.ApiClient(configuration))
        self._days_requested = settings.plaid_days_requested

    def create_link_token(self, user_id: str, access_token: str | None = None) -> dict[str, str]:
        args: dict[str, Any] = dict(
            client_name="Rent an Agent",
            language="en",
            country_codes=[CountryCode("US")],
            user=LinkTokenCreateRequestUser(client_user_id=user_id),
        )
        if access_token:
            # Update mode: the person signs in to the same bank again.
            args["access_token"] = access_token
        else:
            args["products"] = [Products("transactions")]
            args["transactions"] = LinkTokenTransactions(days_requested=self._days_requested)
        response = self._call(self._client.link_token_create, LinkTokenCreateRequest(**args))
        return {"link_token": response["link_token"], "expiration": str(response["expiration"])}

    def exchange_public_token(self, public_token: str) -> tuple[str, str]:
        response = self._call(
            self._client.item_public_token_exchange,
            ItemPublicTokenExchangeRequest(public_token=public_token),
        )
        return response["access_token"], response["item_id"]

    def get_accounts(self, access_token: str) -> list[dict[str, Any]]:
        response = self._call(
            self._client.accounts_get, AccountsGetRequest(access_token=access_token)
        )
        return [_plain(a.to_dict()) for a in response["accounts"]]

    def sync_transactions(self, access_token: str, cursor: str | None) -> SyncPage:
        args: dict[str, Any] = dict(
            access_token=access_token,
            count=500,
            options=TransactionsSyncRequestOptions(include_personal_finance_category=True),
        )
        if cursor:
            args["cursor"] = cursor
        response = self._call(self._client.transactions_sync, TransactionsSyncRequest(**args))
        data = response.to_dict()
        return SyncPage(
            added=[_plain(t) for t in data.get("added", [])],
            modified=[_plain(t) for t in data.get("modified", [])],
            removed=[r["transaction_id"] for r in data.get("removed", [])],
            next_cursor=data["next_cursor"],
            has_more=bool(data["has_more"]),
            update_status=str(data.get("transactions_update_status", "")),
        )

    def create_sandbox_public_token(self, username: str = "user_transactions_dynamic") -> str:
        """Sandbox shortcut that skips the Link UI. Used by scripts/sandbox_smoke.py."""
        request = SandboxPublicTokenCreateRequest(
            institution_id="ins_109508",  # First Platypus Bank, a Plaid sandbox institution
            initial_products=[Products("transactions")],
            options=SandboxPublicTokenCreateRequestOptions(
                override_username=username,
                override_password="pass_good",
                transactions=SandboxPublicTokenCreateRequestOptionsTransactions(
                    days_requested=self._days_requested
                ),
            ),
        )
        return self._call(self._client.sandbox_public_token_create, request)["public_token"]

    @staticmethod
    def _call(method, request):
        try:
            return method(request)
        except plaid.ApiException as exc:
            raise _translate(exc) from None


def _translate(exc: plaid.ApiException) -> BankError:
    try:
        body = json.loads(exc.body or "{}")
    except (TypeError, ValueError):
        body = {}
    plaid_code = body.get("error_code")
    return BankError(_PLAID_CODES.get(plaid_code, "unknown"), plaid_code)


def _plain(value: Any) -> Any:
    """Make SDK output JSON-safe (dates become ISO strings, enums become strings)."""
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
