"""Versioned SurrealQL migrations applied in order and recorded in ``_migration``.

Migration files live in a directory and are named ``NNNN_snake_name.surql``.
Each file is applied exactly once; a changed checksum on an already-applied
file is an error, because the schema the database has no longer matches the
schema the repository describes.
"""

import hashlib
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from surrealmem.shared.infrastructure.surreal.connection import (
    SurrealConnection,
    run_one,
    run_script,
)

if TYPE_CHECKING:
    from pathlib import Path

MIGRATION_TABLE = "_migration"
_FILENAME = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z0-9_]+)\.surql$")

_ENSURE_TABLE = f"""
DEFINE TABLE IF NOT EXISTS {MIGRATION_TABLE} SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS version ON {MIGRATION_TABLE} TYPE int;
DEFINE FIELD IF NOT EXISTS name ON {MIGRATION_TABLE} TYPE string;
DEFINE FIELD IF NOT EXISTS checksum ON {MIGRATION_TABLE} TYPE string;
DEFINE FIELD IF NOT EXISTS applied_at ON {MIGRATION_TABLE} TYPE datetime DEFAULT time::now();
DEFINE INDEX IF NOT EXISTS {MIGRATION_TABLE}_version ON {MIGRATION_TABLE} FIELDS version UNIQUE;
"""


class MigrationError(RuntimeError):
    """The migration set or the database state is inconsistent."""


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    path: Path
    sql: str
    checksum: str


@dataclass(frozen=True, slots=True)
class AppliedMigration:
    version: int
    name: str
    checksum: str


@dataclass(frozen=True, slots=True)
class MigrationStatus:
    migration: Migration
    applied: bool
    checksum_matches: bool


def discover(directory: Path) -> list[Migration]:
    """Load every migration file in ``directory`` ordered by version."""
    if not directory.is_dir():
        raise MigrationError(f"migrations directory does not exist: {directory}")
    found: dict[int, Migration] = {}
    for path in sorted(directory.iterdir()):
        match = _FILENAME.match(path.name)
        if match is None:
            if path.suffix == ".surql":
                raise MigrationError(f"migration file name is not NNNN_name.surql: {path.name}")
            continue
        version = int(match.group("version"))
        if version in found:
            raise MigrationError(f"duplicate migration version {version:04d}: {path.name}")
        sql = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        found[version] = Migration(version, match.group("name"), path, sql, checksum)
    return [found[v] for v in sorted(found)]


async def ensure_table(db: SurrealConnection) -> None:
    await run_script(db, _ENSURE_TABLE)


async def applied(db: SurrealConnection) -> dict[int, AppliedMigration]:
    await ensure_table(db)
    rows = cast(
        "list[dict[str, Any]]",
        await run_one(db, f"SELECT version, name, checksum FROM {MIGRATION_TABLE} ORDER BY version")
        or [],
    )
    return {
        int(row["version"]): AppliedMigration(int(row["version"]), row["name"], row["checksum"])
        for row in rows
    }


async def status(db: SurrealConnection, migrations: list[Migration]) -> list[MigrationStatus]:
    done = await applied(db)
    return [
        MigrationStatus(
            migration=m,
            applied=m.version in done,
            checksum_matches=(m.version not in done or done[m.version].checksum == m.checksum),
        )
        for m in migrations
    ]


async def apply_pending(db: SurrealConnection, migrations: list[Migration]) -> list[Migration]:
    """Apply every migration not yet recorded; return the ones applied in this call."""
    done = await applied(db)
    newly_applied: list[Migration] = []
    for migration in migrations:
        previous = done.get(migration.version)
        if previous is not None:
            if previous.checksum != migration.checksum:
                raise MigrationError(
                    f"migration {migration.version:04d}_{migration.name} was applied with a "
                    "different checksum; create a new migration instead of editing this one"
                )
            continue
        await run_script(db, migration.sql)
        await run_one(
            db,
            f"CREATE {MIGRATION_TABLE} CONTENT "
            "{ version: $version, name: $name, checksum: $checksum }",
            {"version": migration.version, "name": migration.name, "checksum": migration.checksum},
        )
        newly_applied.append(migration)
    return newly_applied
