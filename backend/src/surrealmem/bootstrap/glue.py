"""Cross-slice adapters that only the composition root may know about.

The extraction slice talks to messages and to the knowledge graph through ports; these classes
implement those ports on top of the conversations and knowledge slices.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from surrealmem.conversations.application import AppendMessage, StartConversation
from surrealmem.conversations.domain import (
    ConversationRepository,
    ExtractionStatus,
    NewConversation,
    NewMessage,
    Role,
)
from surrealmem.extraction.domain import ExtractionContext, WrittenEntity
from surrealmem.knowledge.domain import (
    BaseType,
    EntityNotFound,
    NewEntity,
    NewFact,
    NewRelationship,
    ProvenanceRepository,
    RelationshipRepository,
)
from surrealmem.shared.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from surrealmem.curation.domain import ImportedConversation
    from surrealmem.knowledge.application import AddFact, AddRelationship, UpsertEntity

log = get_logger("surrealmem.glue")


@dataclass(slots=True)
class ConversationMessageSource:
    conversations: ConversationRepository
    relationships: RelationshipRepository

    async def extraction_context(self, message_id: str, *, window: int) -> ExtractionContext | None:
        message = await self.conversations.get_message(message_id)
        if message is None:
            return None
        conversation = await self.conversations.get(message.conversation_id)
        if conversation is None:
            return None
        standalone = message.metadata.get("source") == "hindsight" and bool(
            message.metadata.get("fact_type")
        )
        earlier = (
            await self.conversations.messages(
                message.conversation_id, limit=window, before_seq=message.seq
            )
            if window > 0 and not standalone
            else []
        )
        kinds = [k.kind for k in await self.relationships.kinds() if not k.proposed]
        return ExtractionContext(
            message_id=message.id,
            conversation_id=message.conversation_id,
            space=message.space,
            agent_id=conversation.agent_id,
            role=message.role.value,
            content=message.content,
            sent_at=message.created_at,
            window=[(m.role.value, m.content) for m in earlier],
            known_kinds=kinds,
        )

    async def mark(self, message_id: str, status: str) -> None:
        await self.conversations.set_extraction_status(message_id, ExtractionStatus(status))


@dataclass(frozen=True, slots=True)
class _Written:
    id: str
    name: str


@dataclass(slots=True)
class KnowledgeMemoryWriter:
    upsert_entity_uc: UpsertEntity
    add_relationship_uc: AddRelationship
    add_fact_uc: AddFact
    provenance: ProvenanceRepository
    model_name: str | None = None

    async def upsert_entity(
        self,
        *,
        name: str,
        base_type: str,
        subtype: str | None,
        description: str | None,
        aliases: Sequence[str],
        space: str,
        confidence: float,
        seen_at: datetime,
        message_id: str,
        extractor: str,
    ) -> WrittenEntity | None:
        try:
            typed = BaseType(base_type)
        except ValueError:
            return None
        entity, _created = await self.upsert_entity_uc(
            NewEntity(
                name=name,
                base_type=typed,
                subtype=subtype,
                description=description,
                aliases=list(aliases),
                space=space,
                confidence=confidence,
                seen_at=seen_at,
            )
        )
        await self.provenance.link_mention(message_id, entity.id, confidence=confidence)
        await self.provenance.link_source(
            entity.id, message_id, extractor=extractor, model=self.model_name, confidence=confidence
        )
        return _Written(id=entity.id, name=entity.name)

    async def add_relationship(
        self,
        *,
        source_id: str,
        target_id: str,
        kind: str,
        confidence: float,
        space: str,
        message_id: str,
        extractor: str,
    ) -> str | None:
        try:
            relationship = await self.add_relationship_uc(
                NewRelationship(
                    source_id=source_id,
                    target_id=target_id,
                    kind=kind,
                    confidence=confidence,
                    space=space,
                )
            )
        except (ValueError, EntityNotFound) as exc:
            log.warning("relationship.skipped", kind=kind, error=str(exc))
            return None
        await self.provenance.link_source(
            relationship.id,
            message_id,
            extractor=extractor,
            model=self.model_name,
            confidence=confidence,
        )
        return relationship.id

    async def add_fact(
        self,
        *,
        statement: str,
        subject_id: str,
        kind: str,
        object_id: str | None,
        object_literal: str | None,
        category: str | None,
        confidence: float,
        valid_from: datetime | None,
        valid_to: datetime | None,
        recorded_at: datetime,
        space: str,
        message_id: str,
        extractor: str,
    ) -> str | None:
        try:
            fact = await self.add_fact_uc(
                NewFact(
                    statement=statement,
                    space=space,
                    subject_id=subject_id,
                    kind=kind,
                    object_id=object_id,
                    object_literal=object_literal,
                    category=category,
                    confidence=confidence,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    recorded_at=recorded_at,
                )
            )
        except (ValueError, EntityNotFound) as exc:
            log.warning("fact.skipped", kind=kind, error=str(exc))
            return None
        await self.provenance.link_source(
            fact.id, message_id, extractor=extractor, model=self.model_name, confidence=confidence
        )
        return fact.id


@dataclass(slots=True)
class ConversationImportSink:
    """Writes imported conversations through the normal use cases (so extraction jobs queue up)."""

    conversations: ConversationRepository
    start: StartConversation
    append: AppendMessage

    async def import_conversation(
        self, conversation: ImportedConversation, *, space: str, agent_id: str, extract: bool
    ) -> tuple[str, int, bool]:
        existing = await self.conversations.find_external(agent_id, conversation.external_id)
        if existing is not None:
            return existing.id, 0, False
        created = await self.start(
            NewConversation(
                space=space,
                agent_id=agent_id,
                title=conversation.title,
                external_id=conversation.external_id,
                metadata=conversation.metadata,
            )
        )
        append = AppendMessage(self.conversations, self.append.jobs, extract=extract)
        written = 0
        for message in conversation.messages:
            try:
                role = Role(message.role)
            except ValueError:
                role = Role.USER
            await append(
                created.id,
                NewMessage(
                    role=role,
                    content=message.content,
                    created_at=message.created_at,
                    metadata=message.metadata,
                ),
            )
            written += 1
        return created.id, written, True
