"""Opening SurrealDB connections and running multi-statement scripts safely.

The SDK's ``query()`` returns only the first statement's result and does not
surface errors from later statements, so every multi-statement script goes
through :func:`run_script`, which inspects the status of each statement.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from surrealdb import AsyncSurreal

from surrealmem.shared.infrastructure.config import EMBEDDED_SCHEMES
from surrealmem.shared.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

type SurrealConnection = Any  # the SDK returns one of three connection classes

log = get_logger("surrealmem.surreal")

#: Attribute under which the credentials are kept on the SDK connection object, so a session
#: can be re-established after the SDK silently replaces its WebSocket.
_CONFIG_ATTR = "_surrealmem_config"
_AUTH_LOST_MARKERS = ("anonymous access", "not enough permissions", "authentication")


@dataclass(frozen=True, slots=True)
class SurrealConfig:
    """Everything needed to open and scope a connection."""

    url: str
    namespace: str
    database: str
    user: str = "root"
    password: str = "root"

    @property
    def is_embedded(self) -> bool:
        return self.url.startswith(EMBEDDED_SCHEMES)


_TXN_GENERIC = "not executed due to a failed transaction"


class ScriptError(RuntimeError):
    """A statement inside a script returned an error status."""

    def __init__(self, index: int, message: str, statement_preview: str) -> None:
        self.index = index
        self.message = message
        self.statement_preview = statement_preview
        super().__init__(f"statement {index + 1} failed: {message} -- {statement_preview}")


async def open_connection(config: SurrealConfig) -> SurrealConnection:
    """Connect, authenticate (remote engines only) and select namespace/database."""
    # The SDK picks the connection class in a metaclass ``__call__``; type it as a plain factory.
    factory = cast("Callable[..., SurrealConnection]", AsyncSurreal)
    db = factory(url=config.url)
    await db.connect()
    remember_config(db, config)
    await reauthenticate(db)
    return db


def remember_config(db: SurrealConnection, config: SurrealConfig) -> None:
    """Keep the credentials with the connection so the session can be rebuilt later."""
    setattr(db, _CONFIG_ATTR, config)


async def reauthenticate(db: SurrealConnection) -> bool:
    """Sign in again and reselect namespace/database.

    The SDK's WebSocket engine reconnects on its own when the server closes the socket (for
    example "client stopped reading its notifications" during a busy boot), but the new socket
    is a new, anonymous server-side session: every statement then fails with
    "Anonymous access not allowed". Returns False when no credentials are known.
    """
    config = cast("SurrealConfig | None", getattr(db, _CONFIG_ATTR, None))
    if config is None:
        return False
    if not config.is_embedded:
        await db.signin({"username": config.user, "password": config.password})
    await db.use(config.namespace, config.database)
    return True


def is_auth_lost(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _AUTH_LOST_MARKERS)


def _split_preview(sql: str, index: int) -> str:
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    if index < len(statements):
        return statements[index][:80]
    return "<unknown statement>"


async def run_script(
    db: SurrealConnection,
    sql: str,
    variables: Mapping[str, Any] | None = None,
) -> list[Any]:
    """Execute ``sql`` (one or many statements) and return every statement's result.

    Raises :class:`ScriptError` for the first statement whose status is not ``OK``. When the
    failure says the session is anonymous, the connection is re-authenticated and the script
    retried once.
    """
    try:
        return await _run_script_once(db, sql, variables)
    except ScriptError as exc:
        if not is_auth_lost(exc.message):
            raise
        if not await reauthenticate(db):
            raise
        log.warning("surreal.session_restored", reason=exc.message[:120])
        return await _run_script_once(db, sql, variables)


async def _run_script_once(
    db: SurrealConnection,
    sql: str,
    variables: Mapping[str, Any] | None = None,
) -> list[Any]:
    raw = await db.query_raw(sql, dict(variables) if variables else None)
    if "error" in raw:
        # Whole-script failure (for example a parse error): no statement ran.
        error = cast("dict[str, Any]", raw["error"])
        raise ScriptError(0, str(error.get("message", error)), _split_preview(sql, 0))
    outcomes = cast("list[dict[str, Any]]", raw["result"])
    failures = [
        (i, str(o.get("result"))) for i, o in enumerate(outcomes) if o.get("status") != "OK"
    ]
    if failures:
        # Inside a failed transaction every statement reports the generic message; prefer the
        # statement that carries the real cause.
        specific = [f for f in failures if _TXN_GENERIC not in f[1]]
        index, message = specific[0] if specific else failures[0]
        raise ScriptError(index, message, _split_preview(sql, index))
    return [o.get("result") for o in outcomes]


async def run_one(
    db: SurrealConnection,
    sql: str,
    variables: Mapping[str, Any] | None = None,
) -> Any:
    """Execute a single statement and return its result."""
    results = await run_script(db, sql, variables)
    return results[0] if results else None
