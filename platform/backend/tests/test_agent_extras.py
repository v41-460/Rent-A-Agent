"""The /api/agents/<slug>/x/... proxy to an agent's own endpoints."""

from .conftest import signup


def test_needs_login(client):
    assert client.get("/api/agents/hello/x/whoami").status_code == 401


def test_needs_rental(client):
    signup(client)
    r = client.get("/api/agents/hello/x/whoami")
    assert r.status_code == 403


def test_user_comes_from_session(client):
    me = signup(client, name="Zoë").json()["user"]
    rental = client.post("/api/agents/hello/rent").json()["rental_id"]
    got = client.get(
        "/api/agents/hello/x/whoami",
        headers={"X-Rent-User-Id": "someone-else", "X-Rent-Rental-Id": "fake"},
    ).json()
    assert got["x-rent-user-id"] == me["id"]
    assert got["x-rent-rental-id"] == rental
    assert got["x-rent-user-name"] == "Zo%C3%AB"


def test_body_and_query_pass_through(client):
    signup(client)
    client.post("/api/agents/hello/rent")
    got = client.post("/api/agents/hello/x/echo?a=1", json={"x": 2}).json()
    assert got == {"body": {"x": 2}, "query": "a=1"}


def test_cannot_escape_to_run_or_other_paths(client):
    signup(client)
    client.post("/api/agents/hello/rent")
    for path in ("%2e%2e/run", "..%2frun", "a/%2e%2e/%2e%2e/run", "", "a//b"):
        r = client.post(f"/api/agents/hello/x/{path}", json={})
        assert r.status_code == 404, path


def test_agent_without_extras_is_404(client):
    signup(client)
    client.post("/api/agents/paid-helper/rent")
    assert client.get("/api/agents/paid-helper/x/anything").status_code == 404


def test_unknown_extra_path_is_agent_404(client):
    signup(client)
    client.post("/api/agents/hello/rent")
    assert client.get("/api/agents/hello/x/nope").status_code == 404
