"""The fixture agents used by these tests must themselves follow the shared interface."""

from rent_agent_interface import check_agent_app

from .conftest import FIXTURE_AGENTS


def test_hello_fixture_conforms(client):  # the client fixture loads the registry first
    from hello_agent import router

    out = check_agent_app(router, FIXTURE_AGENTS / "hello" / "manifest.json")
    assert out.status == "ok"
