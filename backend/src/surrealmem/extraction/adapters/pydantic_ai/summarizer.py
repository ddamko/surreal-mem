"""Conversation summarizer on pydantic-ai (plain text output)."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

if TYPE_CHECKING:
    from pydantic_ai.models import Model

    from surrealmem.extraction.domain.reflection import ConversationSlice

INSTRUCTIONS = """\
Summarize the conversation excerpt for an agent's long-term memory. Write 3 to 8 sentences in the
third person: what the user wanted, what was decided or learned, open questions, and anything the
agent should remember next time. Keep names, numbers, dates and file paths exact. No preamble.
"""


@dataclass(slots=True)
class PydanticAISummarizer:
    model: Model
    name: str = "llm"
    max_tokens: int = 700
    _agent: Agent[None, str] | None = field(default=None, repr=False)

    @property
    def model_name(self) -> str:
        return self.name

    def agent(self) -> Agent[None, str]:
        if self._agent is None:
            self._agent = Agent(
                self.model,
                instructions=INSTRUCTIONS,
                model_settings=ModelSettings(temperature=0.2, max_tokens=self.max_tokens),
            )
        return self._agent

    async def summarize(self, conversation: ConversationSlice) -> str:
        lines: list[str] = []
        if conversation.previous_summary:
            lines.append(f"Earlier summary: {conversation.previous_summary}\n")
        lines.append(f"Conversation (space {conversation.space}, agent {conversation.agent_id}):")
        for role, content in conversation.messages:
            lines.append(f"[{role}] {content.strip()[:3000]}")
        result = await self.agent().run("\n".join(lines))
        return str(result.output)
