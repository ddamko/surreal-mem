"""Turn one message into entities, relationships and facts with provenance."""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from surrealmem.shared.domain import normalize_name

if TYPE_CHECKING:
    from surrealmem.extraction.domain import (
        ExtractionContext,
        ExtractionResult,
        Extractor,
        MemoryWriter,
        MessageSource,
    )

BASE_TYPES = frozenset({"person", "organization", "location", "event", "object", "concept"})
_TYPE_ALIASES = {
    "people": "person",
    "human": "person",
    "user": "person",
    "company": "organization",
    "org": "organization",
    "team": "organization",
    "place": "location",
    "city": "location",
    "country": "location",
    "meeting": "event",
    "decision": "event",
    "tool": "object",
    "software": "object",
    "library": "object",
    "repository": "object",
    "product": "object",
    "technology": "concept",
    "topic": "concept",
    "idea": "concept",
    "skill": "concept",
}


def canonical_base_type(value: str) -> str | None:
    cleaned = value.strip().lower()
    if cleaned in BASE_TYPES:
        return cleaned
    return _TYPE_ALIASES.get(cleaned)


def parse_date(value: str | None) -> datetime | None:
    """Accept ISO dates and datetimes, YYYY-MM and YYYY; return None for anything else."""
    if not value:
        return None
    text = value.strip()
    if re.fullmatch(r"\d{4}", text):
        text = f"{text}-01-01"
    elif re.fullmatch(r"\d{4}-\d{2}", text):
        text = f"{text}-01"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


@dataclass(slots=True)
class ExtractionReport:
    message_id: str
    extractor: str
    entities: int = 0
    entities_created: int = 0
    relationships: int = 0
    facts: int = 0
    skipped: list[str] = field(default_factory=list[str])

    def as_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "extractor": self.extractor,
            "entities": self.entities,
            "relationships": self.relationships,
            "facts": self.facts,
            "skipped": self.skipped,
        }


@dataclass(slots=True)
class ExtractMessage:
    messages: MessageSource
    extractor: Extractor
    writer: MemoryWriter
    window: int = 6

    async def __call__(self, message_id: str) -> ExtractionReport:
        context = await self.messages.extraction_context(message_id, window=self.window)
        if context is None:
            raise LookupError(f"message not found: {message_id}")
        await self.messages.mark(message_id, "running")
        try:
            result = await self.extractor.extract(context)
        except Exception:
            await self.messages.mark(message_id, "failed")
            raise
        report = await self.write(context, result)
        await self.messages.mark(message_id, "done")
        return report

    async def write(self, context: ExtractionContext, result: ExtractionResult) -> ExtractionReport:
        report = ExtractionReport(message_id=context.message_id, extractor=self.extractor.name)
        ids: dict[str, str] = {}

        for item in result.entities:
            base_type = canonical_base_type(item.base_type)
            if base_type is None or not item.name.strip():
                report.skipped.append(f"entity {item.name!r}: unknown type {item.base_type!r}")
                continue
            written = await self.writer.upsert_entity(
                name=item.name,
                base_type=base_type,
                subtype=item.subtype,
                description=item.description,
                aliases=item.aliases,
                space=context.space,
                confidence=item.confidence,
                seen_at=context.sent_at,
                message_id=context.message_id,
                extractor=self.extractor.name,
            )
            if written is None:
                report.skipped.append(f"entity {item.name!r}: rejected")
                continue
            report.entities += 1
            for key in (item.name, written.name, *item.aliases):
                ids.setdefault(normalize_name(key), written.id)

        for rel in result.relations:
            source = ids.get(normalize_name(rel.source))
            target = ids.get(normalize_name(rel.target))
            if source is None or target is None or source == target:
                report.skipped.append(f"relation {rel.source!r} -{rel.kind}-> {rel.target!r}")
                continue
            written_id = await self.writer.add_relationship(
                source_id=source,
                target_id=target,
                kind=rel.kind,
                confidence=rel.confidence,
                space=context.space,
                message_id=context.message_id,
                extractor=self.extractor.name,
            )
            if written_id is not None:
                report.relationships += 1

        for fact in result.facts:
            subject = ids.get(normalize_name(fact.subject))
            if subject is None:
                report.skipped.append(f"fact {fact.statement!r}: unknown subject {fact.subject!r}")
                continue
            object_id = ids.get(normalize_name(fact.object)) if fact.object else None
            literal = fact.object_literal
            if fact.object and object_id is None and literal is None:
                literal = fact.object
            if object_id == subject:
                object_id = None
            fact_id = await self.writer.add_fact(
                statement=fact.statement,
                subject_id=subject,
                kind=fact.kind,
                object_id=object_id,
                object_literal=literal,
                category=fact.category,
                confidence=fact.confidence,
                valid_from=parse_date(fact.valid_from),
                valid_to=parse_date(fact.valid_to),
                recorded_at=context.sent_at,
                space=context.space,
                message_id=context.message_id,
                extractor=self.extractor.name,
            )
            if fact_id is not None:
                report.facts += 1
        return report
