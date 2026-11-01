from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rent_platform.config import Settings
from rent_platform.main import create_app

FIXTURE_AGENTS = Path(__file__).parent / "fixtures" / "agents"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="sqlite:///:memory:",
        agents_dir=FIXTURE_AGENTS,
        remote_agent_shared_secret="test-secret",
    )


@pytest.fixture
def client(settings) -> TestClient:
    return TestClient(create_app(settings))


def signup(client: TestClient, email="ann@example.com", password="correct horse", name="Ann"):
    return client.post(
        "/api/auth/signup", json={"email": email, "password": password, "display_name": name}
    )
