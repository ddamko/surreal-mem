"""Ports for the reflection job (ADR-0013): summaries, contradictions, salience."""

from typing import TYPE_CHECKING, Any, Protocol

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from datetime import datetime


class ConversationSlice(BaseModel):
    """Messages of a conversation that have not been summarized yet."""

    conversation_id: str
    space: str
    agent_id: str
    from_seq: int
    to_seq: int
    messages: list[tuple[str, str]] = Field(default_factory=list[tuple[str, str]])
    previous_summary: str | None = None


class Summarizer(Protocol):
    @property
    def model_name(self) -> str: ...

    async def summarize(self, conversation: ConversationSlice) -> str: ...


class ReflectionSource(Protocol):
    async def idle_conversations(
        self, *, idle_seconds: int, min_new_messages: int, limit: int
    ) -> list[str]:
        """Conversations with unsummarized messages idle for longer than ``idle_seconds``."""
        ...

    async def unsummarized(
        self, conversation_id: str, *, max_messages: int
    ) -> ConversationSlice | None: ...

    async def contradictions(self) -> list[dict[str, Any]]:
        """Groups of active facts sharing subject, kind and category for functional kinds."""
        ...


class ReflectionWriter(Protocol):
    async def write_summary(
        self,
        conversation: ConversationSlice,
        content: str,
        *,
        model: str,
        embedding: list[float] | None,
        embedding_model: str | None,
    ) -> str: ...

    async def write_observation(
        self,
        *,
        space: str,
        kind: str,
        content: str,
        about: list[str],
        facts: list[str],
        confidence: float = 1.0,
        embedding: list[float] | None = None,
        embedding_model: str | None = None,
    ) -> str: ...

    async def flag_facts(self, fact_ids: list[str], flag: str) -> None: ...

    async def recompute_salience(self, *, now: datetime | None = None) -> int: ...

    async def archive_stale(self, *, salience_floor: float, min_age_days: int) -> int: ...
