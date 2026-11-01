from pathlib import Path

from cryptography.fernet import Fernet
from rent_agent_interface import check_agent_app

import bills_agent
from bills_agent.config import Settings

AGENT_DIR = Path(__file__).resolve().parents[2]


def test_follows_shared_interface(tmp_path):
    bills_agent.configure(
        Settings(
            bills_database_url=f"sqlite:///{tmp_path / 'b.db'}",
            bills_token_encryption_key=Fernet.generate_key().decode(),
            _env_file=None,
        )
    )
    result = check_agent_app(bills_agent.router, AGENT_DIR / "manifest.json")
    assert result.status == "needs_input"
