"""Bills' own storage, separate from the platform's (see AGENTS.md). Every row has a user."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class PlaidItem(Base):
    """One connected bank login for one user."""

    __tablename__ = "bills_plaid_items"

    item_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    # Encrypted. Never leaves the backend.
    access_token_encrypted: Mapped[str] = mapped_column(Text)
    institution_id: Mapped[str | None] = mapped_column(String, nullable=True)
    institution_name: Mapped[str] = mapped_column(String, default="your bank")
    # "ok", "reconnect_needed", or "sample" (practice data, no bank behind it)
    status: Mapped[str] = mapped_column(String, default="ok")
    sync_cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Account(Base):
    __tablename__ = "bills_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String, index=True)
    item_id: Mapped[str] = mapped_column(
        ForeignKey("bills_plaid_items.item_id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    mask: Mapped[str | None] = mapped_column(String, nullable=True)
    type: Mapped[str | None] = mapped_column(String, nullable=True)
    subtype: Mapped[str | None] = mapped_column(String, nullable=True)

    @property
    def label(self) -> str:
        return f"{self.name} (...{self.mask})" if self.mask else self.name


class StoredTransaction(Base):
    """A transaction exactly as Plaid sent it. Detection always re-reads the raw form."""

    __tablename__ = "bills_transactions"
    __table_args__ = (UniqueConstraint("user_id", "transaction_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_id: Mapped[str] = mapped_column(String, index=True)
    item_id: Mapped[str] = mapped_column(
        ForeignKey("bills_plaid_items.item_id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(String, index=True)
    account_id: Mapped[str] = mapped_column(String)
    raw: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DetectionRun(Base):
    __tablename__ = "bills_detection_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    as_of: Mapped[str] = mapped_column(String)
    transaction_count: Mapped[int] = mapped_column(Integer)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    """Every decision the agent makes and every choice the user makes, in order."""

    __tablename__ = "bills_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # "agent", "user" or "system"
    actor: Mapped[str] = mapped_column(String)
    event: Mapped[str] = mapped_column(String, index=True)
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class Database:
    def __init__(self, url: str) -> None:
        if url.startswith("sqlite:///") and ":memory:" not in url:
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, connect_args=connect_args)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    def session(self) -> Iterator[Session]:
        with self.sessions() as session:
            yield session
