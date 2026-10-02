"""Runtime settings loaded from the environment (prefix ``SURREALMEM_``)."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[5]
_DEFAULT_MIGRATIONS_DIR = _REPO_ROOT / "surreal" / "migrations"

EMBEDDED_SCHEMES = ("mem://", "memory", "file://", "surrealkv://", "surrealkv+versioned://")


class Settings(BaseSettings):
    """All configuration for the API, worker, MCP server and CLI."""

    model_config = SettingsConfigDict(
        env_prefix="SURREALMEM_",
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # SurrealDB
    surreal_url: str = "ws://127.0.0.1:8000/rpc"
    surreal_namespace: str = "surrealmem"
    surreal_database: str = "memory"
    surreal_user: str = "root"
    surreal_pass: SecretStr = SecretStr("root")
    migrations_dir: Path = _DEFAULT_MIGRATIONS_DIR

    # API
    api_host: str = "127.0.0.1"
    api_port: int = 8787
    api_token: SecretStr = SecretStr("change-me")

    # Inference
    llm_base_url: str = "http://127.0.0.1:8081/v1"
    llm_model: str = "qwen3-30b-a3b-instruct"
    llm_fallback_base_url: str | None = None
    llm_fallback_model: str | None = None
    llm_fallback_api_key: SecretStr | None = None
    embed_base_url: str = "http://127.0.0.1:8082/v1"
    embed_model: str = "qwen3-embedding-0.6b"
    embed_dimension: int = Field(default=1024, ge=1)

    # Observability
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = True
    otel_enabled: bool = False

    @property
    def surreal_is_embedded(self) -> bool:
        """True when the SurrealDB URL points at an in-process engine."""
        return self.surreal_url.startswith(EMBEDDED_SCHEMES)
