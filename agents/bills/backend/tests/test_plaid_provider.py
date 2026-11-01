"""The real Plaid adapter, checked without network access.

These make sure our requests are valid Plaid SDK objects and that Plaid errors
become calm, specific messages. The live sandbox is exercised by
scripts/sandbox_smoke.py once Plaid keys are configured.
"""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import plaid
import pytest

from bills_agent.bank import BankError, PlaidProvider
from bills_agent.config import Settings


@pytest.fixture
def provider():
    return PlaidProvider(Settings(plaid_client_id="id", plaid_secret="secret", _env_file=None))


def test_needs_keys():
    with pytest.raises(BankError) as err:
        PlaidProvider(Settings(_env_file=None))
    assert err.value.code == "not_configured"


def test_link_token_request(provider, monkeypatch):
    seen = {}

    def fake(request):
        seen["request"] = request.to_dict()
        return {"link_token": "link-sandbox-abc", "expiration": "2026-10-04T10:00:00Z"}

    monkeypatch.setattr(provider._client, "link_token_create", fake)
    assert provider.create_link_token("local-user")["link_token"] == "link-sandbox-abc"
    request = seen["request"]
    assert request["products"] == ["transactions"]
    assert request["transactions"] == {"days_requested": 730}
    assert request["user"] == {"client_user_id": "local-user"}

    provider.create_link_token("local-user", access_token="access-sandbox-x")
    update = seen["request"]
    assert update["access_token"] == "access-sandbox-x"
    assert "products" not in update


def test_sync_request_and_response(provider, monkeypatch):
    seen = {}

    def fake(request):
        seen["request"] = request.to_dict()
        return SimpleNamespace(
            to_dict=lambda: {
                "added": [
                    {
                        "transaction_id": "t1",
                        "date": date(2026, 9, 5),
                        "amount": 15.49,
                        "name": "NETFLIX.COM",
                        "personal_finance_category": {"primary": "ENTERTAINMENT"},
                    }
                ],
                "modified": [],
                "removed": [{"transaction_id": "t0"}],
                "next_cursor": "c1",
                "has_more": False,
                "transactions_update_status": "HISTORICAL_UPDATE_COMPLETE",
            }
        )

    monkeypatch.setattr(provider._client, "transactions_sync", fake)
    page = provider.sync_transactions("access-sandbox-x", None)
    assert "cursor" not in seen["request"]
    assert seen["request"]["options"]["include_personal_finance_category"] is True
    assert page.added[0]["date"] == "2026-09-05"
    assert page.removed == ["t0"]
    json.dumps(page.added)  # stored as JSON, so it must serialize


@pytest.mark.parametrize(
    "plaid_code, ours",
    [
        ("ITEM_LOGIN_REQUIRED", "reconnect_needed"),
        ("INSTITUTION_NOT_RESPONDING", "bank_unavailable"),
        ("INVALID_LINK_TOKEN", "link_expired"),
        ("PRODUCT_NOT_READY", "still_loading"),
        ("SOMETHING_NEW", "unknown"),
    ],
)
def test_plaid_errors_become_friendly(provider, monkeypatch, plaid_code, ours):
    def fail(request):
        exc = plaid.ApiException(status=400, reason="Bad Request")
        exc.body = json.dumps({"error_code": plaid_code, "error_type": "ITEM_ERROR"})
        raise exc

    monkeypatch.setattr(provider._client, "accounts_get", fail)
    with pytest.raises(BankError) as err:
        provider.get_accounts("access-sandbox-x")
    assert err.value.code == ours
    assert err.value.plaid_code == plaid_code
    assert "Plaid" not in err.value.message
