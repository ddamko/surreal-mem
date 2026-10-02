"""Conversation use cases: start, append (and enqueue extraction), read back."""

from dataclasses import dataclass

from surrealmem.conversations.domain import (
    Conversation,
    ConversationNotFound,
    ConversationRepository,
    ConversationStatus,
    ExtractionStatus,
    Message,
    NewConversation,
    NewMessage,
    Role,
)
from surrealmem.shared.application import JobQueue, JobRequest
from surrealmem.shared.domain import validate_space

EXTRACTABLE_ROLES = frozenset({Role.USER, Role.ASSISTANT})


@dataclass(slots=True)
class StartConversation:
    conversations: ConversationRepository

    async def __call__(self, data: NewConversation) -> Conversation:
        validate_space(data.space)
        if data.external_id is not None:
            existing = await self.conversations.find_external(data.agent_id, data.external_id)
            if existing is not None:
                return existing
        return await self.conversations.create(data)


@dataclass(slots=True)
class AppendMessage:
    """Store a message and queue its extraction (ADR-0011)."""

    conversations: ConversationRepository
    jobs: JobQueue
    extract: bool = True

    async def __call__(self, conversation_id: str, data: NewMessage) -> Message:
        conversation = await self.conversations.get(conversation_id)
        if conversation is None:
            raise ConversationNotFound(conversation_id)
        message = await self.conversations.append_message(conversation_id, data)
        if self.extract and message.role in EXTRACTABLE_ROLES:
            await self.jobs.enqueue(
                JobRequest(
                    kind="extract",
                    payload={
                        "message_id": message.id,
                        "conversation_id": conversation_id,
                        "space": conversation.space,
                    },
                    dedupe_key=f"extract:{message.id}",
                )
            )
            await self.conversations.set_extraction_status(message.id, ExtractionStatus.QUEUED)
            message = message.model_copy(update={"extraction_status": ExtractionStatus.QUEUED})
        else:
            await self.conversations.set_extraction_status(message.id, ExtractionStatus.SKIPPED)
            message = message.model_copy(update={"extraction_status": ExtractionStatus.SKIPPED})
        return message


@dataclass(frozen=True, slots=True)
class ConversationView:
    conversation: Conversation
    messages: list[Message]


@dataclass(slots=True)
class GetConversation:
    conversations: ConversationRepository

    async def __call__(
        self, conversation_id: str, *, limit: int = 100, before_seq: int | None = None
    ) -> ConversationView:
        conversation = await self.conversations.get(conversation_id)
        if conversation is None:
            raise ConversationNotFound(conversation_id)
        messages = await self.conversations.messages(
            conversation_id, limit=limit, before_seq=before_seq
        )
        return ConversationView(conversation=conversation, messages=messages)


@dataclass(slots=True)
class ListConversations:
    conversations: ConversationRepository

    async def __call__(
        self,
        *,
        space: str | None = None,
        agent_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        return await self.conversations.list(
            space=space, agent_id=agent_id, limit=limit, offset=offset
        )


@dataclass(slots=True)
class CloseConversation:
    conversations: ConversationRepository

    async def __call__(self, conversation_id: str) -> None:
        if await self.conversations.get(conversation_id) is None:
            raise ConversationNotFound(conversation_id)
        await self.conversations.set_status(conversation_id, ConversationStatus.CLOSED)
