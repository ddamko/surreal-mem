"""Deterministic fictional dataset for CI, screenshots and demos (never real memories)."""

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from surrealmem.curation.domain import (
    ImportedConversation,
    ImportedMessage,
    ImportReport,
    ImportSink,
)

PEOPLE = [
    "Mara Voss",
    "Teodor Lind",
    "Priya Natarajan",
    "Jonas Berg",
    "Lucia Ferreira",
    "Kenji Abe",
]
ORGS = ["Helix Robotics", "Northwind Labs", "Quill & Sons", "Bluefin Analytics"]
PLACES = ["Lisbon", "Oslo", "Austin", "Kyoto", "Montreal"]
TOOLS = ["SurrealDB", "Angular", "Nushell", "Three.js", "pydantic-ai", "llama.cpp", "Playwright"]
TOPICS = ["knowledge graphs", "vector search", "entity resolution", "reflection jobs", "dashboards"]

TEMPLATES = [
    ("user", "Quick intro: I'm {p1}, I work at {o1} in {pl1}. I'm building a {topic} prototype."),
    ("assistant", "Nice to meet you, {p1}. {o1} in {pl1}, noted. What stack are you using?"),
    (
        "user",
        "Mostly {t1} and {t2}. My teammate {p2} prefers {t3}, but we agreed on {t1} last week.",
    ),
    ("assistant", "Got it: {t1} for the core, {t2} alongside, and {p2} prefers {t3}."),
    (
        "user",
        "Also remember that {p2} reports to {p3}, and {o1} is opening an office in {pl2} in 2027.",
    ),
    ("assistant", "Stored: {p2} reports to {p3}; {o1} plans a {pl2} office in 2027."),
    (
        "user",
        "One preference: I like concise answers with code blocks, and I use tabs for indentation.",
    ),
    ("assistant", "Understood. Concise answers, code blocks, tabs."),
]


@dataclass(slots=True)
class SyntheticGenerator:
    sink: ImportSink
    seed: int = 7

    def conversations(
        self, count: int, *, start: datetime | None = None
    ) -> list[ImportedConversation]:
        rng = random.Random(self.seed)
        start = start or datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
        result: list[ImportedConversation] = []
        for index in range(count):
            people = rng.sample(PEOPLE, 3)
            tools = rng.sample(TOOLS, 3)
            places = rng.sample(PLACES, 2)
            fill = {
                "p1": people[0],
                "p2": people[1],
                "p3": people[2],
                "o1": rng.choice(ORGS),
                "pl1": places[0],
                "pl2": places[1],
                "t1": tools[0],
                "t2": tools[1],
                "t3": tools[2],
                "topic": rng.choice(TOPICS),
            }
            when = start + timedelta(days=index * 3)
            messages = [
                ImportedMessage(
                    role=role, content=text.format(**fill), created_at=when + timedelta(minutes=i)
                )
                for i, (role, text) in enumerate(TEMPLATES)
            ]
            result.append(
                ImportedConversation(
                    external_id=f"synthetic:{self.seed}:{index}",
                    title=f"Synthetic conversation {index + 1}",
                    messages=messages,
                    metadata={"source": "synthetic", "seed": self.seed},
                )
            )
        return result

    async def run(self, *, space: str, count: int = 5, extract: bool = True) -> ImportReport:
        report = ImportReport(source="synthetic", space=space)
        for conversation in self.conversations(count):
            _, written, created = await self.sink.import_conversation(
                conversation, space=space, agent_id="synthetic", extract=extract
            )
            if created:
                report.conversations += 1
                report.messages += written
            else:
                report.skipped += 1
        return report
