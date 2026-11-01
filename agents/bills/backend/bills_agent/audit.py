from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .db import AuditEvent


def record(
    session: Session,
    user_id: str,
    actor: str,
    event: str,
    subject: str | None = None,
    **details: Any,
) -> None:
    """Append to the audit log. The caller commits. Never pass secrets in ``details``."""
    session.add(
        AuditEvent(user_id=user_id, actor=actor, event=event, subject=subject, details=details)
    )
