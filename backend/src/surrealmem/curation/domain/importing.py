"""Importing memories from other systems: ports and the import report."""

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field


class ImportedMessage(BaseModel):
    role: str
    content: str
    created_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict[str, Any])


class ImportedConversation(BaseModel):
    external_id: str
    title: str | None = None
    messages: list[ImportedMessage] = Field(default_factory=list[ImportedMessage])
    metadata: dict[str, Any] = Field(default_factory=dict[str, Any])


class ImportSink(Protocol):
    """Where imported conversations go (the conversations slice, via the composition root)."""

    async def import_conversation(
        self, conversation: ImportedConversation, *, space: str, agent_id: str, extract: bool
    ) -> tuple[str, int, bool]:
        """Return (conversation id, messages written, created); known external ids are skipped."""
        ...


class ImportReport(BaseModel):
    source: str
    space: str
    conversations: int = 0
    messages: int = 0
    skipped: int = 0
    notes: list[str] = Field(default_factory=list[str])
