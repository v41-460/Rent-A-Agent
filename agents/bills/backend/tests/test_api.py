"""The Bills endpoints, served the way the platform serves them: /run plus /x/... with the
user named in X-Rent-User-Id."""

from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

import bills_agent
from bills_agent import api
from bills_agent.bank import BankError
from bills_agent.config import Settings
from bills_agent.db import AuditEvent, PlaidItem
from bills_fixtures import scenarios

from .fake_bank import ACCESS_TOKEN, FakeBank

ANN = {"X-Rent-User-Id": "user-ann"}
BOB = {"X-Rent-User-Id": "user-bob"}


@pytest.fixture
def household():
    return scenarios.typical_household()


@pytest.fixture
def bank(household):
    return FakeBank(household.transactions)


def make_settings(tmp_path, **overrides) -> Settings:
    values = dict(
        plaid_client_id="test",
        plaid_secret="test",
        bills_database_url=f"sqlite:///{tmp_path / 'bills.db'}",
        bills_token_encryption_key=Fernet.generate_key().decode(),
        _env_file=None,
    )
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def client(tmp_path, bank, household):
    bills_agent.configure(make_settings(tmp_path), bank=bank, today=lambda: household.as_of)
    app = FastAPI()
    app.include_router(bills_agent.router)
    app.include_router(bills_agent.extra_router, prefix="/x")
    return TestClient(app)


def connect(client, headers=ANN):
    assert client.post("/x/link/token", json={}, headers=headers).json()["link_token"]
    response = client.post(
        "/x/link/exchange",
        headers=headers,
        json={
            "public_token": "public-sandbox-ok",
            "institution": {"institution_id": "ins_109508", "name": "First Platypus Bank"},
        },
    )
    assert response.status_code == 200, response.text
    return response


def run(client, user="user-ann"):
    return client.post(
        "/run", json={"user": {"id": user, "display_name": "X"}, "rental_id": "r1", "input": {}}
    ).json()


def test_connect_sync_and_detect_end_to_end(client, household):
    assert client.get("/x/bills", headers=ANN).json() == {"status": "not_run"}
    assert connect(client).json() == {"connected": True, "institution_name": "First Platypus Bank"}
    assert client.post("/x/sync", headers=ANN).json()["status"] == "ready"

    bills = client.get("/x/bills", headers=ANN).json()
    assert bills["transaction_count"] == len(household.transactions)
    by_name = {b["payee"]: b for b in bills["bills"]}
    assert set(by_name) == {e.payee for e in household.bills}
    rent = by_name["Oakwood Apts Rent"]
    assert rent["typical_amount"] == "1450.00"
    assert rent["next_due"] == "2026-10-01"
    assert rent["frequency"] == "monthly"
    assert rent["bucket"] == "due_soon"
    assert by_name["Xfinity"]["bucket"] == "upcoming"


def test_requests_without_a_user_are_refused(client):
    for path in ("/x/bills", "/x/connection"):
        assert client.get(path).status_code == 401
    for path in ("/x/sync", "/x/sample", "/x/disconnect"):
        assert client.post(path).status_code == 401


def test_users_never_see_each_others_bank(client):
    connect(client, ANN)
    client.post("/x/sync", headers=ANN)
    assert client.get("/x/bills", headers=BOB).json() == {"status": "not_run"}
    assert client.get("/x/connection", headers=BOB).json()["connected"] is False
    assert client.post("/x/sync", headers=BOB).json() == {"status": "not_connected"}
    assert run(client, "user-bob")["status"] == "needs_input"
    # Bob disconnecting must not touch Ann.
    client.post("/x/disconnect", headers=BOB)
    assert client.get("/x/bills", headers=ANN).json()["status"] == "ready"


def test_same_practice_data_for_two_users_does_not_collide(client):
    assert client.post("/x/sample", headers=ANN).json()["status"] == "ready"
    assert client.post("/x/sample", headers=BOB).json()["status"] == "ready"
    a = client.get("/x/bills", headers=ANN).json()
    b = client.get("/x/bills", headers=BOB).json()
    assert a["transaction_count"] == b["transaction_count"] > 0
    assert [x["payee"] for x in a["bills"]] == [x["payee"] for x in b["bills"]]


def test_practice_data_is_shifted_to_today(client, household):
    client.post("/x/sample", headers=ANN)
    bills = client.get("/x/bills", headers=ANN).json()
    assert bills["as_of"] == household.as_of.isoformat()  # fixture clock = household.as_of
    assert client.get("/x/connection", headers=ANN).json()["banks"][0]["status"] == "sample"


def test_real_bank_replaces_practice_data(client, household):
    client.post("/x/sample", headers=ANN)
    connect(client)
    banks = client.get("/x/connection", headers=ANN).json()["banks"]
    assert [b["status"] for b in banks] == ["ok"]
    client.post("/x/sync", headers=ANN)
    assert client.get("/x/bills", headers=ANN).json()["transaction_count"] == len(
        household.transactions
    )


def test_practice_data_refused_when_bank_connected(client):
    connect(client)
    r = client.post("/x/sample", headers=ANN)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "already_connected"


def test_disconnect_forgets_everything(client):
    connect(client)
    client.post("/x/sync", headers=ANN)
    client.post("/x/disconnect", headers=ANN)
    assert client.get("/x/connection", headers=ANN).json()["connected"] is False
    assert client.get("/x/bills", headers=ANN).json() == {"status": "not_run"}


def test_run_returns_bill_blocks(client, household):
    assert run(client)["status"] == "needs_input"
    connect(client)
    client.post("/x/sync", headers=ANN)
    out = run(client)
    assert out["status"] == "ok"
    items = out["blocks"][1]["items"]
    rent = next(i for i in items if i["title"] == "Oakwood Apts Rent")
    assert rent["value"] == "$1,450.00"
    assert rent["subtitle"] == "Every month, next due Oct 1"


def test_access_token_never_leaves_the_backend(client):
    responses = [
        client.post("/x/link/token", json={}, headers=ANN),
        connect(client),
        client.post("/x/sync", headers=ANN),
        client.get("/x/bills", headers=ANN),
        client.get("/x/connection", headers=ANN),
        client.get("/health"),
    ]
    for response in responses:
        assert ACCESS_TOKEN not in response.text
        assert "access-sandbox" not in response.text
    st = api.state()
    with st.db.sessions() as session:
        item = session.scalars(select(PlaidItem)).one()
        assert ACCESS_TOKEN not in item.access_token_encrypted
        assert st.vault.open(item.access_token_encrypted) == ACCESS_TOKEN
        for event in session.scalars(select(AuditEvent)):
            assert ACCESS_TOKEN not in json.dumps(event.details)


def test_every_detection_is_audited_per_user(client, household):
    connect(client)
    client.post("/x/sync", headers=ANN)
    with api.state().db.sessions() as session:
        events = session.scalars(select(AuditEvent)).all()
    assert {e.user_id for e in events} == {"user-ann"}
    kinds = [e.event for e in events]
    assert kinds[0] == "bank_connected"
    detected = {e.subject for e in events if e.event == "bill_detected"}
    assert detected == {e.payee for e in household.bills}


def test_sync_pages_through_everything(client, bank, household):
    bank.page_size = 37
    connect(client)
    client.post("/x/sync", headers=ANN)
    count = client.get("/x/bills", headers=ANN).json()["transaction_count"]
    assert count == len(household.transactions)


def test_sync_restarts_when_data_changes_mid_pagination(client, bank, household):
    bank.page_size = 100
    bank.fail_next_sync = [BankError("unknown", "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION")]
    connect(client)
    assert client.post("/x/sync", headers=ANN).json()["status"] == "ready"


def test_removed_transactions_are_dropped(client, bank, household):
    connect(client)
    client.post("/x/sync", headers=ANN)
    netflix = [t["transaction_id"] for t in household.transactions if t["name"] == "NETFLIX.COM"]
    bank.removed = netflix
    client.post("/x/sync", headers=ANN)
    bills = client.get("/x/bills", headers=ANN).json()
    assert bills["transaction_count"] == len(household.transactions) - len(netflix)
    assert "Netflix" not in {b["payee"] for b in bills["bills"]}


def test_transactions_still_loading(client, bank):
    bank.not_ready = True
    connect(client)
    response = client.post("/x/sync", headers=ANN).json()
    assert response["status"] == "still_loading"
    assert "still sending" in response["message"]


def test_reconnect_needed_then_reconnected(client, bank):
    connect(client)
    client.post("/x/sync", headers=ANN)
    bank.fail_next_sync = [BankError("reconnect_needed", "ITEM_LOGIN_REQUIRED")]
    response = client.post("/x/sync", headers=ANN).json()
    assert response["status"] == "reconnect_needed"
    assert "sign in again" in response["message"]
    assert client.get("/x/bills", headers=ANN).json()["bills"]  # earlier bills still shown
    client.post("/x/link/token", json={"reconnect": True}, headers=ANN)
    assert bank.link_tokens[-1] == ACCESS_TOKEN
    client.post("/x/link/reconnected", headers=ANN)
    assert client.get("/x/connection", headers=ANN).json()["banks"][0]["status"] == "ok"
    assert client.post("/x/sync", headers=ANN).json()["status"] == "ready"


def test_bank_outage_is_a_calm_message_not_a_crash(client, bank):
    connect(client)
    bank.fail_next_sync = [BankError("bank_unavailable", "INSTITUTION_NOT_RESPONDING")]
    response = client.post("/x/sync", headers=ANN)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "bank_unavailable"


def test_expired_public_token(client):
    r = client.post("/x/link/exchange", json={"public_token": "public-sandbox-old"}, headers=ANN)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "link_expired"


def test_link_events_are_logged(client):
    client.post(
        "/x/link/event",
        headers=ANN,
        json={"event": "exit", "error_code": "INSTITUTION_DOWN", "institution_name": "Bank"},
    )
    with api.state().db.sessions() as session:
        event = session.scalars(select(AuditEvent)).one()
    assert event.event == "link_exit" and event.user_id == "user-ann"


def test_only_sandbox_is_allowed():
    with pytest.raises(ValueError):
        Settings(plaid_env="production", _env_file=None)
    with pytest.raises(ValueError):
        Settings(plaid_env="development", _env_file=None)


def test_works_without_plaid_keys_using_practice_data(tmp_path, household):
    settings = make_settings(
        tmp_path, plaid_client_id="", plaid_secret="", bills_token_encryption_key=""
    )
    bills_agent.configure(settings, today=lambda: household.as_of)
    app = FastAPI()
    app.include_router(bills_agent.extra_router, prefix="/x")
    client = TestClient(app)
    conn = client.get("/x/connection", headers=ANN).json()
    assert conn["bank_available"] is False
    r = client.post("/x/link/token", json={}, headers=ANN)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "not_configured"
    assert client.post("/x/sample", headers=ANN).json()["status"] == "ready"
    assert client.post("/x/sync", headers=ANN).json()["status"] == "ready"
