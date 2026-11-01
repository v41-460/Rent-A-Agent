"""Email + password accounts with an httpOnly session cookie."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

import bcrypt
from fastapi import HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db import LoginSession, User, utcnow

COOKIE = "ra_session"
MIN_PASSWORD = 8


def hash_password(password: str) -> str:
    # bcrypt only uses the first 72 bytes; pre-hash so long passphrases still count fully.
    digest = hashlib.sha256(password.encode()).hexdigest().encode()
    return bcrypt.hashpw(digest, bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    digest = hashlib.sha256(password.encode()).hexdigest().encode()
    return bcrypt.checkpw(digest, hashed.encode())


# Used so a login for an unknown email takes as long as a wrong password.
_DUMMY_HASH = hash_password("not-a-real-password")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(db: Session, response: Response, user: User, days: int, secure: bool) -> None:
    token = secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            token_hash=_token_hash(token),
            user_id=user.id,
            expires_at=utcnow() + timedelta(days=days),
        )
    )
    db.commit()
    response.set_cookie(
        COOKIE,
        token,
        max_age=days * 86400,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )


def end_session(db: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == _token_hash(token)))
        db.commit()
    response.delete_cookie(COOKIE, path="/")


def current_user(db: Session, request: Request) -> User | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    row = db.get(LoginSession, _token_hash(token))
    if row is None or row.expires_at < utcnow():
        return None
    return db.get(User, row.user_id)


def require_user(db: Session, request: Request) -> User:
    user = current_user(db, request)
    if user is None:
        raise HTTPException(
            401, detail={"code": "not_logged_in", "message": "Please log in first."}
        )
    return user


def find_by_email(db: Session, email: str) -> User | None:
    return db.scalars(select(User).where(User.email == email.strip().lower())).first()
