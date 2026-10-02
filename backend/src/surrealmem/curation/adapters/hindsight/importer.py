"""Turn Hindsight documents and memories into conversations for our own extraction pipeline.

Two sources per bank:

* **documents** carry the original transcripts (``original_text`` is a JSON list of role/content
  messages). Each becomes a conversation keyed ``hindsight:<bank>:doc:<id>``.
* **memories** are Hindsight's extracted statements (world / experience / observation). They are
  grouped by their session tag into conversations keyed ``hindsight:<bank>:session:<tag>`` and
  stored as user messages carrying the Hindsight metadata, so our extractor re-types the entities
  and produces facts with provenance back to these messages.
"""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from surrealmem.curation.domain import (
    ImportedConversation,
    ImportedMessage,
    ImportReport,
    ImportSink,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from surrealmem.curation.adapters.hindsight.client import HindsightClient

_SESSION_TAG = re.compile(r"^session:(.+)$")
_NOISE_PREFIXES = ("[IMPORTANT: You are running as a scheduled cron job",)


def _when(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_transcript(original_text: str) -> list[ImportedMessage]:
    """Hindsight stores retained transcripts as JSON: a (sometimes nested) list of role/content."""
    try:
        data = json.loads(original_text)
    except json.JSONDecodeError:
        return (
            [ImportedMessage(role="user", content=original_text)] if original_text.strip() else []
        )
    flat: list[Any] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in cast("list[Any]", node):
                walk(item)
        elif isinstance(node, dict):
            flat.append(node)

    walk(data)
    messages: list[ImportedMessage] = []
    for item in flat:
        entry = cast("dict[str, Any]", item)
        role = str(entry.get("role") or "user").lower()
        content = entry.get("content")
        if isinstance(content, list):
            content = "\n".join(
                str(cast("dict[str, Any]", part).get("text", ""))
                for part in cast("list[Any]", content)
                if isinstance(part, dict)
            )
        text = str(content or "").strip()
        if not text or role not in {"user", "assistant", "system", "tool"}:
            continue
        if text.startswith("User: "):
            text = text[6:]
        if any(text.startswith(p) for p in _NOISE_PREFIXES):
            continue
        messages.append(ImportedMessage(role=role, content=text))
    return messages


def session_tag(tags: list[str] | None) -> str | None:
    for tag in tags or []:
        match = _SESSION_TAG.match(str(tag))
        if match:
            return match.group(1)
    return None


@dataclass(slots=True)
class HindsightImporter:
    client: HindsightClient
    sink: ImportSink
    agent_id: str = "hermes"

    async def documents(self, bank_id: str) -> AsyncIterator[ImportedConversation]:
        async for summary in self.client.documents(bank_id):
            document = await self.client.document(bank_id, str(summary["id"]))
            messages = parse_transcript(str(document.get("original_text") or ""))
            created = _when(document.get("created_at"))
            for message in messages:
                message.created_at = created
            meta = cast("dict[str, Any]", document.get("document_metadata") or {})
            yield ImportedConversation(
                external_id=f"hindsight:{bank_id}:doc:{document['id']}",
                title=str(meta.get("session_id") or document["id"]),
                messages=messages,
                metadata={
                    "source": "hindsight",
                    "bank": bank_id,
                    "document_id": document["id"],
                    "platform": meta.get("platform"),
                    "tags": document.get("tags") or [],
                },
            )

    async def memory_sessions(self, bank_id: str) -> AsyncIterator[ImportedConversation]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        async for memory in self.client.memories(bank_id):
            if memory.get("state") not in (None, "valid"):
                continue
            key = session_tag(cast("list[str] | None", memory.get("tags"))) or "untagged"
            grouped.setdefault(key, []).append(memory)
        for key, memories in grouped.items():
            memories.sort(key=lambda m: str(m.get("mentioned_at") or m.get("date") or ""))
            yield ImportedConversation(
                external_id=f"hindsight:{bank_id}:session:{key}",
                title=f"Hindsight memories {key}",
                messages=[
                    ImportedMessage(
                        role="user",
                        content=str(m["text"]),
                        created_at=_when(m.get("mentioned_at") or m.get("date")),
                        metadata={
                            "source": "hindsight",
                            "hindsight_id": m.get("id"),
                            "fact_type": m.get("fact_type"),
                            "entities": [
                                e.strip()
                                for e in str(m.get("entities") or "").split(",")
                                if e.strip()
                            ],
                            "occurred_start": m.get("occurred_start"),
                            "occurred_end": m.get("occurred_end"),
                            "document_id": m.get("document_id"),
                        },
                    )
                    for m in memories
                    if str(m.get("text") or "").strip()
                ],
                metadata={"source": "hindsight", "bank": bank_id, "session": key},
            )

    async def run(
        self,
        bank_id: str,
        *,
        space: str,
        include_documents: bool = True,
        include_memories: bool = True,
        extract: bool = True,
        limit: int | None = None,
    ) -> ImportReport:
        report = ImportReport(source=f"hindsight:{bank_id}", space=space)
        sources: list[AsyncIterator[ImportedConversation]] = []
        if include_documents:
            sources.append(self.documents(bank_id))
        if include_memories:
            sources.append(self.memory_sessions(bank_id))
        for source in sources:
            async for conversation in source:
                if limit is not None and report.conversations >= limit:
                    return report
                if not conversation.messages:
                    report.skipped += 1
                    continue
                _, written, created = await self.sink.import_conversation(
                    conversation, space=space, agent_id=self.agent_id, extract=extract
                )
                if created:
                    report.conversations += 1
                    report.messages += written
                else:
                    report.skipped += 1
        return report
