"""Runtime settings loaded from the environment (prefix ``SURREALMEM_``)."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
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
    api_port: int = 8790
    api_token: SecretStr = SecretStr("change-me")
    dashboard_dist: Path | None = _REPO_ROOT / "dashboard" / "dist" / "dashboard" / "browser"

    # Inference
    llm_base_url: str = "http://127.0.0.1:8081/v1"
    llm_model: str = "qwen3-30b-a3b-instruct"
    llm_api_key: SecretStr | None = None
    llm_temperature: float = 0.1
    llm_max_tokens: int = 2500
    llm_timeout_seconds: float = 180.0
    llm_fallback_base_url: str | None = None
    llm_fallback_model: str | None = None
    llm_fallback_api_key: SecretStr | None = None
    embed_base_url: str = "http://127.0.0.1:8082/v1"
    embed_model: str = "qwen3-embedding-0.6b"
    embed_dimension: int = Field(default=1024, ge=1)
    embed_api_key: SecretStr | None = None

    # Defaults for agents that do not say who they are (MCP stdio, hooks)
    default_space: str = "personal"
    default_agent_id: str = "agent"
    default_user_name: str = "User"

    # Extraction and resolution
    extraction_window: int = Field(default=6, ge=0, le=50)
    resolution_auto_merge: float = Field(default=0.92, ge=0.0, le=1.0)
    resolution_review: float = Field(default=0.80, ge=0.0, le=1.0)

    # Worker and scheduler
    worker_id: str | None = None
    worker_poll_seconds: float = 1.0
    worker_lease_seconds: int = 300
    worker_concurrency: int = Field(default=2, ge=1, le=8)
    schedule_reflect_sweep_seconds: int = 600
    schedule_salience_seconds: int = 1800
    schedule_metrics_seconds: int = 1800
    schedule_project_seconds: int = 3600
    reflection_idle_seconds: int = 900
    reflection_min_new_messages: int = 4

    # Observability
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = True
    otel_enabled: bool = False

    @field_validator("dashboard_dist", mode="before")
    @classmethod
    def _empty_dist_is_none(cls, value: object) -> object:
        """``SURREALMEM_DASHBOARD_DIST=`` disables static serving (containers use nginx)."""
        return None if value in ("", None) else value

    @property
    def surreal_is_embedded(self) -> bool:
        """True when the SurrealDB URL points at an in-process engine."""
        return self.surreal_url.startswith(EMBEDDED_SCHEMES)
