import httpx
import pytest
from fastapi import FastAPI, Request

from rent_platform.registry import SIGNATURE_HEADER, Registry, sign

from .conftest import FIXTURE_AGENTS, signup


def slugs(client):
    return [a["slug"] for a in client.get("/api/agents").json()["agents"]]


def test_lists_valid_agents_without_login(client):
    got = slugs(client)
    assert set(got) == {"hello", "paid-helper", "soon", "broken-backend", "far-away"}
    assert "broken-manifest" not in got


def test_rentable_agents_listed_first(client):
    agents = client.get("/api/agents").json()["agents"]
    flags = [a["rentable"] for a in agents]
    assert flags == sorted(flags, reverse=True)


def test_broken_agents_reported_not_fatal(client):
    problems = client.get("/api/health").json()["problems"]
    assert any("broken-manifest" in p for p in problems)
    assert any("broken-backend" in p for p in problems)
    broken = client.get("/api/agents/broken-backend").json()["agent"]
    assert broken["rentable"] is False


def test_price_text(client):
    by = {a["slug"]: a for a in client.get("/api/agents").json()["agents"]}
    assert by["hello"]["price_text"] == "Free"
    assert by["paid-helper"]["price_text"] == "$4.99 a month"
    assert by["soon"]["price_text"] == "$10.00 one time"


def test_detail_has_long_description_and_404(client):
    assert "long_description" in client.get("/api/agents/hello").json()["agent"]
    r = client.get("/api/agents/nope")
    assert r.status_code == 404


def test_rent_requires_login(client):
    assert client.post("/api/agents/hello/rent").status_code == 401


def test_coming_soon_cannot_be_rented(client):
    signup(client)
    r = client.post("/api/agents/soon/rent")
    assert r.status_code == 409


def test_rent_free_agent_no_payment(client):
    signup(client)
    r = client.post("/api/agents/hello/rent")
    assert r.status_code == 201
    assert r.json()["payment"] is None
    assert client.get("/api/agents/hello").json()["agent"]["rented"] is True


def test_rent_paid_agent_records_mock_payment(client):
    signup(client)
    r = client.post("/api/agents/paid-helper/rent").json()
    assert r["payment"]["amount_cents"] == 499
    assert r["payment"]["provider"] == "mock" and r["payment"]["test_mode"] is True
    from rent_platform.db import Payment

    db = next(client.app.state.db.session())
    assert db.query(Payment).count() == 1


def test_renting_twice_does_not_charge_twice(client):
    signup(client)
    client.post("/api/agents/paid-helper/rent")
    again = client.post("/api/agents/paid-helper/rent").json()
    assert again["already_rented"] is True and again["payment"] is None
    from rent_platform.db import Payment

    db = next(client.app.state.db.session())
    assert db.query(Payment).count() == 1


def test_my_agents(client):
    signup(client)
    client.post("/api/agents/hello/rent")
    got = client.get("/api/rentals").json()["agents"]
    assert [a["slug"] for a in got] == ["hello"]


def test_rentals_are_per_user(client):
    signup(client)
    client.post("/api/agents/hello/rent")
    client.post("/api/auth/logout")
    signup(client, email="bob@example.com", name="Bob")
    assert client.get("/api/rentals").json()["agents"] == []
    assert client.post("/api/agents/hello/run", json={}).status_code == 403


def test_run_requires_rental(client):
    signup(client)
    r = client.post("/api/agents/hello/run", json={"input": {}})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "not_rented"


def test_run_returns_agent_blocks_with_real_user(client):
    me = signup(client).json()["user"]
    rental_id = client.post("/api/agents/hello/rent").json()["rental_id"]
    r = client.post("/api/agents/hello/run", json={"input": {}})
    assert r.status_code == 200
    body = r.json()
    assert body["blocks"][0] == {"type": "heading", "text": "Hello, Ann"}
    assert body["blocks"][1]["text"] == f"user={me['id']} rental={rental_id}"


def test_browser_cannot_pretend_to_be_someone_else(client):
    me = signup(client).json()["user"]
    client.post("/api/agents/hello/rent")
    r = client.post(
        "/api/agents/hello/run",
        json={"input": {}, "user": {"id": "someone-else", "display_name": "Mallory"}},
    )
    assert f"user={me['id']}" in r.json()["blocks"][1]["text"]


def test_agent_breaking_interface_gives_friendly_error(client):
    signup(client)
    client.post("/api/agents/paid-helper/rent")
    r = client.post("/api/agents/paid-helper/run", json={"input": {"bad": True}})
    assert r.status_code == 200
    assert r.json()["status"] == "error"
    assert r.json()["blocks"][0]["type"] == "notice"


# --- remote agents ---


def _fake_remote(secret: str) -> FastAPI:
    app = FastAPI()

    @app.post("/run")
    async def run(request: Request):
        body = await request.body()
        if request.headers.get(SIGNATURE_HEADER) != sign(body, secret):
            return {"status": "error", "message": "bad signature", "blocks": []}
        return {"status": "ok", "blocks": [{"type": "text", "text": "signed ok"}]}

    return app


@pytest.mark.parametrize(("remote_secret", "expected"), [("test-secret", "ok"), ("other", "error")])
def test_remote_agent_requests_are_signed(client, monkeypatch, remote_secret, expected):
    remote = _fake_remote(remote_secret)

    def fake_client(self, entry):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=remote), base_url="http://r")

    monkeypatch.setattr(Registry, "_client", fake_client)
    signup(client)
    client.post("/api/agents/far-away/rent")
    r = client.post("/api/agents/far-away/run", json={"input": {}}).json()
    assert r["status"] == expected


def test_remote_without_secret_configured_fails_safely():
    reg = Registry(FIXTURE_AGENTS, remote_secret="")
    import asyncio

    from rent_agent_interface import RunRequest

    req = RunRequest(user={"id": "u", "display_name": "U"}, rental_id="r")
    out = asyncio.run(reg.run(reg.get("far-away"), req))
    assert out.status == "error"
