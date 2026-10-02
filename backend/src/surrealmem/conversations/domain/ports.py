"""Persistence port for conversations and messages."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from surrealmem.conversations.domain.models import (
        Conversation,
        ConversationStatus,
        ExtractionStatus,
        Message,
        NewConversation,
        NewMessage,
    )


class ConversationNotFound(LookupError):
    pass


class ConversationRepository(Protocol):
    async def create(self, data: NewConversation) -> Conversation: ...

    async def get(self, conversation_id: str) -> Conversation | None: ...

    async def find_external(self, agent_id: str, external_id: str) -> Conversation | None: ...

    async def list(
        self,
        *,
        space: str | None = None,
        agent_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]: ...

    async def set_status(self, conversation_id: str, status: ConversationStatus) -> None: ...

    async def append_message(self, conversation_id: str, data: NewMessage) -> Message:
        """Append with the next sequence number and bump the conversation counters."""
        ...

    async def get_message(self, message_id: str) -> Message | None: ...

    async def messages(
        self,
        conversation_id: str,
        *,
        limit: int = 100,
        before_seq: int | None = None,
    ) -> list[Message]:
        """Messages in ascending sequence order, optionally ending before ``before_seq``."""
        ...

    async def set_extraction_status(self, message_id: str, status: ExtractionStatus) -> None: ...
