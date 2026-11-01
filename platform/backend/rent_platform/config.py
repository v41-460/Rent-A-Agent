from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/platform.db"
    agents_dir: Path = REPO_ROOT / "agents"
    # Cookies are marked Secure in production (HTTPS). Off for localhost development.
    cookie_secure: bool = False
    session_days: int = 30
    remote_agent_shared_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
