from typing import TYPE_CHECKING

from surrealmem.shared.infrastructure.config import Settings

if TYPE_CHECKING:
    import pytest


def test_defaults_point_at_local_stack() -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.surreal_url == "ws://127.0.0.1:8000/rpc"
    assert settings.surreal_is_embedded is False
    assert settings.migrations_dir.name == "migrations"


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SURREALMEM_SURREAL_URL", "mem://")
    monkeypatch.setenv("SURREALMEM_EMBED_DIMENSION", "384")
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.surreal_is_embedded is True
    assert settings.embed_dimension == 384
