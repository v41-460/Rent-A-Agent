from rent_platform.auth import COOKIE, check_password, hash_password

from .conftest import signup


def test_signup_logs_you_in(client):
    r = signup(client)
    assert r.status_code == 201
    assert r.json()["user"]["display_name"] == "Ann"
    assert client.get("/api/auth/me").json()["user"]["email"] == "ann@example.com"


def test_cookie_is_httponly(client):
    r = signup(client)
    cookie = r.headers["set-cookie"].lower()
    assert COOKIE in cookie and "httponly" in cookie and "samesite=lax" in cookie


def test_password_is_hashed_not_stored(client):
    signup(client)
    from rent_platform.db import User

    db = next(client.app.state.db.session())
    user = db.query(User).one()
    assert "correct horse" not in user.password_hash
    assert check_password("correct horse", user.password_hash)


def test_long_password_fully_counts():
    base = "x" * 80
    assert not check_password(base + "a", hash_password(base + "b"))


def test_email_is_case_insensitive(client):
    signup(client, email="Ann@Example.com")
    client.post("/api/auth/logout")
    r = client.post(
        "/api/auth/login", json={"email": "ann@example.COM", "password": "correct horse"}
    )
    assert r.status_code == 200


def test_duplicate_email_rejected_plainly(client):
    signup(client)
    r = signup(client)
    assert r.status_code == 409
    assert "already an account" in r.json()["detail"]["message"]


def test_short_password_rejected(client):
    r = signup(client, password="short")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "password_too_short"


def test_wrong_password_plain_message(client):
    signup(client)
    client.post("/api/auth/logout")
    r = client.post("/api/auth/login", json={"email": "ann@example.com", "password": "nope nope"})
    assert r.status_code == 401
    assert "don't match" in r.json()["detail"]["message"]


def test_unknown_email_same_message_as_wrong_password(client):
    r = client.post("/api/auth/login", json={"email": "who@example.com", "password": "whatever1"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "wrong_login"


def test_logout_ends_session(client):
    signup(client)
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").json()["user"] is None


def test_logout_invalidates_old_cookie_server_side(client):
    signup(client)
    token = client.cookies.get(COOKIE)
    client.post("/api/auth/logout")
    client.cookies.set(COOKIE, token)
    assert client.get("/api/auth/me").json()["user"] is None


def test_garbage_cookie_is_ignored(client):
    client.cookies.set(COOKIE, "made-up")
    assert client.get("/api/auth/me").json()["user"] is None
