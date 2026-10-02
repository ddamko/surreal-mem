"""Structured extraction with pydantic-ai against an OpenAI-compatible model (ADR-0008/0009)."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic_ai import Agent, NativeOutput
from pydantic_ai.settings import ModelSettings

from surrealmem.extraction.domain import ExtractionContext, ExtractionError, ExtractionResult

if TYPE_CHECKING:
    from pydantic_ai.models import Model

INSTRUCTIONS = """\
You extract long-term memory from one message of a conversation between a user and an AI agent.
Return only what the message states or clearly implies. Never invent details.

Entities: every person, organization, location, event, object (tools, software, libraries,
repositories, files, products, devices) and concept (technologies, topics, skills, ideas) that
matters beyond this message. base_type must be exactly one of: person, organization, location,
event, object, concept. Add a short snake_case subtype when obvious (software_library, city,
meeting, decision, git_repository). Use the name as written; put other spellings in aliases.
Skip the AI agent itself unless the user names it, and skip generic words (today, thing, it).

Relations: typed edges between two extracted entities, source and target given by their names.
Prefer the kinds in the provided vocabulary; otherwise write a new UPPER_SNAKE_CASE kind.

Facts: self-contained third-person statements worth remembering later: roles, locations,
dates, decisions, attributes, settings, plans, and preferences. subject must be an extracted
entity name. Use object for an entity, object_literal for a value (a date, a number, a port, a
setting). Preferences use kind PREFERS with a category (shell, editor, indentation, cuisine...).
Give valid_from or valid_to as ISO dates only when the text states when something started or ended.
Set confidence below 1.0 when the text is uncertain or hedged.

Return an empty result when the message carries nothing worth remembering (greetings, chit-chat,
pure tool output).
"""


MAX_TARGET_CHARS = 6000
MAX_WINDOW_CHARS = 800


def build_prompt(context: ExtractionContext) -> str:
    lines = [
        f"Date of the message: {context.sent_at.date().isoformat()}",
        f"Space: {context.space}. Agent: {context.agent_id}.",
    ]
    if context.known_kinds:
        lines.append("Relationship vocabulary: " + ", ".join(context.known_kinds))
    if context.window:
        lines.append("\nEarlier messages (context only, do not extract from them):")
        for role, content in context.window:
            lines.append(f"[{role}] {content.strip()[:MAX_WINDOW_CHARS]}")
    body = context.content.strip()
    if len(body) > MAX_TARGET_CHARS:
        body = body[:MAX_TARGET_CHARS] + "\n[... truncated ...]"
    lines.append(f"\nMessage to extract from ([{context.role}]):\n{body}")
    return "\n".join(lines)


@dataclass(slots=True)
class PydanticAIExtractor:
    model: Model
    extractor_name: str = "llm"
    temperature: float = 0.1
    max_tokens: int = 4096
    retries: int = 2
    _agent: Agent[None, ExtractionResult] | None = field(default=None, repr=False)

    @property
    def name(self) -> str:
        return self.extractor_name

    def agent(self) -> Agent[None, ExtractionResult]:
        if self._agent is None:
            self._agent = Agent(
                self.model,
                output_type=NativeOutput(
                    ExtractionResult,
                    name="extraction",
                    description="Entities, relations and facts extracted from the message.",
                ),
                instructions=INSTRUCTIONS,
                retries=self.retries,
                model_settings=ModelSettings(
                    temperature=self.temperature, max_tokens=self.max_tokens
                ),
            )
        return self._agent

    async def extract(self, context: ExtractionContext) -> ExtractionResult:
        try:
            run = await self.agent().run(build_prompt(context))
        except Exception as exc:
            raise ExtractionError(f"{self.extractor_name}: {exc}") from exc
        return run.output

    def usage_hint(self) -> dict[str, Any]:
        return {"extractor": self.extractor_name, "model": str(self.model.model_name)}
