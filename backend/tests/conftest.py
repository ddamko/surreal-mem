"""Shared fixtures: an embedded SurrealDB per test and the repository migrations."""

import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from surrealmem.shared.infrastructure.surreal import migrations as mig
from surrealmem.shared.infrastructure.surreal.connection import (
    SurrealConfig,
    SurrealConnection,
    open_connection,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "surreal" / "migrations"


@pytest.fixture
def migrations_dir() -> Path:
    return MIGRATIONS_DIR


@pytest.fixture
async def embedded_db() -> AsyncIterator[SurrealConnection]:
    """A fresh in-memory SurrealDB scoped to a unique namespace/database."""
    suffix = uuid.uuid4().hex[:8]
    config = SurrealConfig(url="mem://", namespace=f"test_{suffix}", database="memory")
    db = await open_connection(config)
    try:
        yield db
    finally:
        await db.close()


@pytest.fixture
async def migrated_db(embedded_db: SurrealConnection, migrations_dir: Path) -> SurrealConnection:
    """An embedded database with every repository migration applied."""
    await mig.apply_pending(embedded_db, mig.discover(migrations_dir))
    return embedded_db
