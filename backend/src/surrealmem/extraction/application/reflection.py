"""The reflection job: summarize idle conversations, flag contradictions, refresh salience."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from surrealmem.shared.application import Embedder, JobQueue, JobRequest

if TYPE_CHECKING:
    from surrealmem.extraction.domain.reflection import (
        ReflectionSource,
        ReflectionWriter,
        Summarizer,
    )


@dataclass(slots=True)
class ReflectionReport:
    conversation_id: str | None = None
    summary_id: str | None = None
    summarized_messages: int = 0
    contradictions: int = 0
    salience_updated: int = 0
    archived: int = 0
    enqueued: list[str] = field(default_factory=list[str])

    def as_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "summary_id": self.summary_id,
            "summarized_messages": self.summarized_messages,
            "contradictions": self.contradictions,
            "salience_updated": self.salience_updated,
            "archived": self.archived,
            "enqueued": len(self.enqueued),
        }


@dataclass(slots=True)
class ReflectConversation:
    """Summarize the unsummarized tail of one conversation into a `summary` record."""

    source: ReflectionSource
    writer: ReflectionWriter
    summarizer: Summarizer
    embedder: Embedder | None = None
    max_messages: int = 60

    async def __call__(self, conversation_id: str) -> ReflectionReport:
        report = ReflectionReport(conversation_id=conversation_id)
        tail = await self.source.unsummarized(conversation_id, max_messages=self.max_messages)
        if tail is None or not tail.messages:
            return report
        content = (await self.summarizer.summarize(tail)).strip()
        if not content:
            return report
        embedding: list[float] | None = None
        model: str | None = None
        if self.embedder is not None:
            embedding = (await self.embedder.embed([content]))[0]
            model = self.embedder.model_name
        report.summary_id = await self.writer.write_summary(
            tail,
            content,
            model=self.summarizer.model_name,
            embedding=embedding,
            embedding_model=model,
        )
        report.summarized_messages = len(tail.messages)
        return report


@dataclass(slots=True)
class ReflectionSweep:
    """Periodic pass: enqueue summaries for idle conversations, detect contradictions, refresh
    salience and archive stale facts. Never deletes (ADR-0013)."""

    source: ReflectionSource
    writer: ReflectionWriter
    jobs: JobQueue
    idle_seconds: int = 900
    min_new_messages: int = 4
    max_conversations: int = 50
    salience_floor: float = 0.15
    archive_min_age_days: int = 180

    async def __call__(self) -> ReflectionReport:
        report = ReflectionReport()
        for conversation_id in await self.source.idle_conversations(
            idle_seconds=self.idle_seconds,
            min_new_messages=self.min_new_messages,
            limit=self.max_conversations,
        ):
            job_id = await self.jobs.enqueue(
                JobRequest(
                    kind="reflect",
                    payload={"conversation_id": conversation_id},
                    dedupe_key=f"reflect:{conversation_id}",
                    priority=7,
                )
            )
            report.enqueued.append(job_id)
        for group in await self.source.contradictions():
            fact_ids = [str(f) for f in group["facts"]]
            await self.writer.flag_facts(fact_ids, "contradiction")
            await self.writer.write_observation(
                space=str(group.get("space") or "shared"),
                kind="contradiction",
                content=(
                    f"{group.get('subject_name', group['subject'])} has {len(fact_ids)} active "
                    f"{group['kind']} facts that cannot all hold: "
                    + " | ".join(str(s) for s in group.get("statements", []))
                ),
                about=[str(group["subject"])],
                facts=fact_ids,
                confidence=0.9,
            )
            report.contradictions += 1
        report.salience_updated = await self.writer.recompute_salience()
        report.archived = await self.writer.archive_stale(
            salience_floor=self.salience_floor, min_age_days=self.archive_min_age_days
        )
        return report
