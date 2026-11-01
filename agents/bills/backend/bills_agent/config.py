"""Bills settings, read from agents/bills/backend/.env (never committed) or the environment."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _default_db_url() -> str:
    data_dir = Path(os.environ.get("AGENT_DATA_DIR", BACKEND_DIR / "data"))
    return f"sqlite:///{data_dir / 'bills.db'}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    plaid_client_id: str = ""
    plaid_secret: str = ""
    plaid_env: str = "sandbox"
    # Two years of history lets yearly bills show up twice.
    plaid_days_requested: int = 730

    bills_database_url: str = ""
    # Fernet key that encrypts Plaid access tokens at rest.
    bills_token_encryption_key: str = ""

    @field_validator("plaid_env")
    @classmethod
    def sandbox_only(cls, value: str) -> str:
        # Hard rule for Rent an Agent: no real bank data, no real money. Do not relax this
        # without Vai's explicit approval.
        if value != "sandbox":
            raise ValueError("PLAID_ENV must be 'sandbox' for the Bills agent")
        return value

    @property
    def database_url(self) -> str:
        return self.bills_database_url or _default_db_url()

    @property
    def plaid_configured(self) -> bool:
        return bool(self.plaid_client_id and self.plaid_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
