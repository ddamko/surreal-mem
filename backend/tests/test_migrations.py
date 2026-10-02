from typing import TYPE_CHECKING

import pytest

from surrealmem.shared.infrastructure.surreal import migrations as mig
from surrealmem.shared.infrastructure.surreal.connection import (
    ScriptError,
    SurrealConnection,
    run_one,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write(directory: Path, name: str, sql: str) -> Path:
    path = directory / name
    path.write_text(sql, encoding="utf-8")
    return path


def test_discover_orders_by_version_and_rejects_bad_names(tmp_path: Path) -> None:
    _write(tmp_path, "0002_second.surql", "RETURN 2;")
    _write(tmp_path, "0001_first.surql", "RETURN 1;")
    _write(tmp_path, "notes.md", "ignored")
    versions = [m.version for m in mig.discover(tmp_path)]
    assert versions == [1, 2]

    _write(tmp_path, "bad-name.surql", "RETURN 0;")
    with pytest.raises(mig.MigrationError, match="NNNN_name"):
        mig.discover(tmp_path)


def test_discover_rejects_duplicate_versions(tmp_path: Path) -> None:
    _write(tmp_path, "0001_a.surql", "RETURN 1;")
    _write(tmp_path, "0001_b.surql", "RETURN 1;")
    with pytest.raises(mig.MigrationError, match="duplicate"):
        mig.discover(tmp_path)


async def test_apply_pending_is_idempotent(embedded_db: SurrealConnection, tmp_path: Path) -> None:
    _write(
        tmp_path,
        "0001_widgets.surql",
        "DEFINE TABLE widget SCHEMAFULL; DEFINE FIELD name ON widget TYPE string;",
    )
    _write(tmp_path, "0002_seed.surql", "CREATE widget:one SET name = 'one';")
    migrations = mig.discover(tmp_path)

    first = await mig.apply_pending(embedded_db, migrations)
    assert [m.version for m in first] == [1, 2]
    second = await mig.apply_pending(embedded_db, migrations)
    assert second == []

    rows = await run_one(embedded_db, "SELECT name FROM widget")
    assert rows == [{"name": "one"}]
    recorded = await mig.applied(embedded_db)
    assert sorted(recorded) == [1, 2]


async def test_failed_statement_is_not_recorded(
    embedded_db: SurrealConnection, tmp_path: Path
) -> None:
    _write(
        tmp_path,
        "0001_broken.surql",
        "DEFINE TABLE gadget SCHEMAFULL; DEFINE FIELD n ON gadget TYPE int; "
        "CREATE gadget:x SET n = 'not an int';",
    )
    with pytest.raises(ScriptError, match="statement 3"):
        await mig.apply_pending(embedded_db, mig.discover(tmp_path))
    assert await mig.applied(embedded_db) == {}


async def test_changed_checksum_is_rejected(embedded_db: SurrealConnection, tmp_path: Path) -> None:
    path = _write(tmp_path, "0001_a.surql", "RETURN 1;")
    await mig.apply_pending(embedded_db, mig.discover(tmp_path))
    path.write_text("RETURN 2;", encoding="utf-8")
    with pytest.raises(mig.MigrationError, match="checksum"):
        await mig.apply_pending(embedded_db, mig.discover(tmp_path))
    report = await mig.status(embedded_db, mig.discover(tmp_path))
    assert report[0].applied is True
    assert report[0].checksum_matches is False


async def test_repository_migrations_apply_cleanly(migrated_db: SurrealConnection) -> None:
    info = await run_one(migrated_db, "INFO FOR DB")
    assert "_migration" in info["tables"]
    assert "english" in info["analyzers"]
