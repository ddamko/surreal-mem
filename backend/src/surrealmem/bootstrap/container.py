"""Composition root: wires settings to concrete adapters."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from surrealmem.shared.infrastructure.surreal.connection import (
    SurrealConfig,
    SurrealConnection,
    open_connection,
    run_one,
)

if TYPE_CHECKING:
    from surrealmem.shared.infrastructure.config import Settings


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    db: SurrealConnection

    async def is_ready(self) -> bool:
        try:
            return await run_one(self.db, "RETURN 1") == 1
        except Exception:
            return False

    async def close(self) -> None:
        await self.db.close()


def surreal_config(settings: Settings) -> SurrealConfig:
    return SurrealConfig(
        url=settings.surreal_url,
        namespace=settings.surreal_namespace,
        database=settings.surreal_database,
        user=settings.surreal_user,
        password=settings.surreal_pass.get_secret_value(),
    )


async def build_container(settings: Settings) -> AppContainer:
    db = await open_connection(surreal_config(settings))
    return AppContainer(settings=settings, db=db)
