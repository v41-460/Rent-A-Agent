"""Marketplace HTTP API. Run: uvicorn rent_platform.main:create_app --factory --port 8000"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from rent_agent_interface import RunRequest, RunResponse, RunUser
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import auth
from .config import Settings, get_settings
from .db import Database, Payment, Rental, User
from .registry import AgentEntry, Registry


class SignupBody(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)
    display_name: str = Field(min_length=1, max_length=80)


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)


class RunBody(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def _user_out(user: User) -> dict[str, str]:
    return {"id": user.id, "email": user.email, "display_name": user.display_name}


def _price_text(entry: AgentEntry) -> str:
    p = entry.manifest.pricing
    if p.model == "free":
        return "Free"
    dollars = f"${p.amount_cents / 100:,.2f}"
    return f"{dollars} a month" if p.model == "monthly" else f"{dollars} one time"


def _agent_out(entry: AgentEntry, rented: bool, full: bool = False) -> dict[str, Any]:
    m = entry.manifest
    out: dict[str, Any] = {
        "slug": m.slug,
        "name": m.name,
        "description": m.description,
        "icon": m.icon,
        "pricing": m.pricing.model_dump(),
        "price_text": _price_text(entry),
        "status": m.status,
        "rentable": entry.rentable,
        "rented": rented,
        "has_custom_page": m.has_custom_page,
    }
    if full:
        out["long_description"] = m.long_description
    return out


def create_app(settings: Settings | None = None, registry: Registry | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Rent an Agent")
    app.state.db = Database(settings.database_url)
    app.state.registry = registry or Registry(
        settings.agents_dir, settings.remote_agent_shared_secret
    )

    def db_session(request: Request) -> Iterator[Session]:
        yield from request.app.state.db.session()

    def get_registry(request: Request) -> Registry:
        return request.app.state.registry

    def rented_slugs(db: Session, user: User | None) -> set[str]:
        if user is None:
            return set()
        return set(db.scalars(select(Rental.agent_slug).where(Rental.user_id == user.id)))

    def agent_or_404(reg: Registry, slug: str) -> AgentEntry:
        entry = reg.get(slug)
        if entry is None:
            raise _err(404, "no_such_agent", "We couldn't find that helper.")
        return entry

    # --- health ---

    @app.get("/api/health")
    def health(reg: Registry = Depends(get_registry)) -> dict[str, Any]:
        return {"ok": True, "agents": len(reg.agents), "problems": reg.problems}

    # --- accounts ---

    @app.post("/api/auth/signup", status_code=201)
    def signup(body: SignupBody, response: Response, db: Session = Depends(db_session)):
        if len(body.password) < auth.MIN_PASSWORD:
            raise _err(
                422,
                "password_too_short",
                f"Please choose a password with at least {auth.MIN_PASSWORD} characters.",
            )
        user = User(
            email=body.email.strip().lower(),
            display_name=body.display_name.strip(),
            password_hash=auth.hash_password(body.password),
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise _err(
                409,
                "email_taken",
                "There's already an account with that email. Try logging in instead.",
            ) from None
        auth.start_session(db, response, user, settings.session_days, settings.cookie_secure)
        return {"user": _user_out(user)}

    @app.post("/api/auth/login")
    def login(body: LoginBody, response: Response, db: Session = Depends(db_session)):
        user = auth.find_by_email(db, body.email)
        ok = auth.check_password(body.password, user.password_hash if user else auth._DUMMY_HASH)
        if user is None or not ok:
            raise _err(
                401,
                "wrong_login",
                "That email and password don't match. Please check them and try again.",
            )
        auth.start_session(db, response, user, settings.session_days, settings.cookie_secure)
        return {"user": _user_out(user)}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response, db: Session = Depends(db_session)):
        auth.end_session(db, request, response)
        return {"ok": True}

    @app.get("/api/auth/me")
    def me(request: Request, db: Session = Depends(db_session)):
        user = auth.current_user(db, request)
        return {"user": _user_out(user) if user else None}

    # --- marketplace ---

    @app.get("/api/agents")
    def list_agents(
        request: Request, db: Session = Depends(db_session), reg: Registry = Depends(get_registry)
    ):
        rented = rented_slugs(db, auth.current_user(db, request))
        entries = sorted(reg.agents.values(), key=lambda e: (not e.rentable, e.manifest.name))
        return {"agents": [_agent_out(e, e.slug in rented) for e in entries]}

    @app.get("/api/agents/{slug}")
    def get_agent(
        slug: str,
        request: Request,
        db: Session = Depends(db_session),
        reg: Registry = Depends(get_registry),
    ):
        entry = agent_or_404(reg, slug)
        rented = slug in rented_slugs(db, auth.current_user(db, request))
        return {"agent": _agent_out(entry, rented, full=True)}

    @app.get("/api/rentals")
    def my_rentals(
        request: Request, db: Session = Depends(db_session), reg: Registry = Depends(get_registry)
    ):
        user = auth.require_user(db, request)
        rows = db.scalars(
            select(Rental).where(Rental.user_id == user.id).order_by(Rental.created_at)
        )
        out = []
        for r in rows:
            entry = reg.get(r.agent_slug)
            if entry is not None:
                out.append({**_agent_out(entry, True), "rented_at": r.created_at.isoformat()})
        return {"agents": out}

    @app.post("/api/agents/{slug}/rent", status_code=201)
    def rent(
        slug: str,
        request: Request,
        db: Session = Depends(db_session),
        reg: Registry = Depends(get_registry),
    ):
        user = auth.require_user(db, request)
        entry = agent_or_404(reg, slug)
        if not entry.rentable:
            raise _err(409, "not_available", "This helper isn't ready yet. Check back soon.")
        existing = db.scalars(
            select(Rental).where(Rental.user_id == user.id, Rental.agent_slug == slug)
        ).first()
        if existing:
            return {"rental_id": existing.id, "already_rented": True, "payment": None}
        rental = Rental(user_id=user.id, agent_slug=slug)
        db.add(rental)
        db.flush()
        payment = None
        p = entry.manifest.pricing
        if p.model != "free":
            # MOCK PAYMENT: always succeeds, no money moves. Replace with a real provider later.
            payment = Payment(
                user_id=user.id,
                rental_id=rental.id,
                amount_cents=p.amount_cents,
                currency=p.currency,
                pricing_model=p.model,
            )
            db.add(payment)
        db.commit()
        return {
            "rental_id": rental.id,
            "already_rented": False,
            "payment": (
                {
                    "id": payment.id,
                    "amount_cents": payment.amount_cents,
                    "provider": "mock",
                    "status": payment.status,
                    "test_mode": True,
                }
                if payment
                else None
            ),
        }

    @app.post("/api/agents/{slug}/run", response_model=RunResponse)
    async def run(
        slug: str,
        body: RunBody,
        request: Request,
        db: Session = Depends(db_session),
        reg: Registry = Depends(get_registry),
    ) -> RunResponse:
        user = auth.require_user(db, request)
        entry = agent_or_404(reg, slug)
        rental = db.scalars(
            select(Rental).where(Rental.user_id == user.id, Rental.agent_slug == slug)
        ).first()
        if rental is None:
            raise _err(403, "not_rented", "You'll need to rent this helper before using it.")
        if not entry.runnable:
            raise _err(409, "not_available", "This helper isn't ready yet. Check back soon.")
        # The user always comes from the session, never from the browser's request body.
        req = RunRequest(
            user=RunUser(id=user.id, display_name=user.display_name),
            rental_id=rental.id,
            input=body.input,
        )
        return await reg.run(entry, req)

    return app
