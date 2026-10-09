"""Session recovery after the SDK silently reconnects (anonymous session)."""

from typing import Any

import pytest

from surrealmem.shared.infrastructure.surreal.connection import (
    ScriptError,
    SurrealConfig,
    is_auth_lost,
    remember_config,
    run_script,
)

ANON = "Anonymous access not allowed: Not enough permissions to perform this action"


class _ReconnectingDb:
    """Answers anonymously until ``signin`` is called again, like a replaced WebSocket."""

    def __init__(self, *, authenticated: bool = True) -> None:
        self.authenticated = authenticated
        self.signins = 0
        self.uses: list[tuple[str, str]] = []
        self.queries = 0

    async def signin(self, vars: dict[str, Any]) -> None:
        self.signins += 1
        self.authenticated = True

    async def use(self, namespace: str, database: str) -> None:
        self.uses.append((namespace, database))

    async def query_raw(self, sql: str, variables: dict[str, Any] | None) -> dict[str, Any]:
        self.queries += 1
        if not self.authenticated:
            return {"result": [{"status": "ERR", "result": ANON}]}
        return {"result": [{"status": "OK", "result": [{"n": 1}]}]}


def _config() -> SurrealConfig:
    return SurrealConfig(url="ws://db:8000/rpc", namespace="ns", database="db")


async def test_run_script_reauthenticates_once_and_retries() -> None:
    db = _ReconnectingDb(authenticated=False)
    remember_config(db, _config())
    rows = await run_script(db, "SELECT count() AS n FROM space GROUP ALL")
    assert rows == [[{"n": 1}]]
    assert db.signins == 1 and db.uses == [("ns", "db")] and db.queries == 2


async def test_run_script_without_known_credentials_raises() -> None:
    db = _ReconnectingDb(authenticated=False)
    with pytest.raises(ScriptError, match="Anonymous"):
        await run_script(db, "SELECT 1")
    assert db.signins == 0


async def test_non_auth_errors_are_not_retried() -> None:
    class _Broken(_ReconnectingDb):
        async def query_raw(self, sql: str, variables: dict[str, Any] | None) -> dict[str, Any]:
            self.queries += 1
            return {"result": [{"status": "ERR", "result": "Parse error: unexpected token"}]}

    db = _Broken()
    remember_config(db, _config())
    with pytest.raises(ScriptError, match="Parse error"):
        await run_script(db, "SELEC 1")
    assert db.queries == 1 and db.signins == 0


def test_is_auth_lost_markers() -> None:
    assert is_auth_lost(ANON)
    assert is_auth_lost("There was a problem with authentication")
    assert not is_auth_lost("Parse error")
