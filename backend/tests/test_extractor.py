import json
from datetime import UTC, datetime
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from surrealmem.extraction.adapters.pydantic_ai.extractor import PydanticAIExtractor, build_prompt
from surrealmem.extraction.domain import ExtractionContext


def _context() -> ExtractionContext:
    return ExtractionContext(
        message_id="message:1",
        conversation_id="conversation:1",
        space="work",
        agent_id="claude-code",
        role="user",
        content="I'm Derek and I maintain surreal-mem.",
        sent_at=datetime(2026, 10, 2, tzinfo=UTC),
        window=[("assistant", "Hi there")],
        known_kinds=["WORKS_AT", "MAINTAINS"],
    )


def test_prompt_contains_window_kinds_and_message() -> None:
    prompt = build_prompt(_context())
    assert "2026-10-02" in prompt
    assert "WORKS_AT, MAINTAINS" in prompt
    assert "[assistant] Hi there" in prompt
    assert prompt.rstrip().endswith("I'm Derek and I maintain surreal-mem.")


async def test_extractor_parses_native_structured_output() -> None:
    payload: dict[str, Any] = {
        "entities": [
            {
                "name": "Derek",
                "base_type": "person",
                "subtype": None,
                "description": None,
                "aliases": [],
                "confidence": 1.0,
            },
            {
                "name": "surreal-mem",
                "base_type": "object",
                "subtype": "git_repository",
                "description": None,
                "aliases": [],
                "confidence": 0.9,
            },
        ],
        "relations": [
            {"source": "Derek", "kind": "MAINTAINS", "target": "surreal-mem", "confidence": 0.9}
        ],
        "facts": [],
    }

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        assert info.output_tools == []
        return ModelResponse(parts=[TextPart(json.dumps(payload))])

    extractor = PydanticAIExtractor(model=FunctionModel(respond), extractor_name="test")
    result = await extractor.extract(_context())
    assert [e.name for e in result.entities] == ["Derek", "surreal-mem"]
    assert result.relations[0].kind == "MAINTAINS"
    assert result.facts == []
    assert extractor.name == "test"
