"""Claude Code hook handlers (ADR-0027).

Each handler takes the JSON Claude Code pipes to a hook and returns the JSON (or None) to print.
SessionStart opens or resumes a conversation keyed by the Claude session id, UserPromptSubmit stores
the prompt and injects a budgeted context pack, Stop stores the assistant's last reply.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from surrealmem.conversations.domain import Conversation, NewConversation, NewMessage, Role
from surrealmem.retrieval.domain import RetrievalQuery
from surrealmem.shared.domain import validate_space

if TYPE_CHECKING:
    from surrealmem.bootstrap.services import Services

AGENT_ID = "claude-code"


def space_for(payload: dict[str, Any], *, override: str | None) -> str:
    """``project:<directory name>`` unless an explicit space was configured."""
    if override:
        return validate_space(override)
    cwd = str(payload.get("cwd") or Path.cwd())
    name = Path(cwd).name.lower()
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in name).strip("-")
    return validate_space(f"project:{cleaned or 'root'}")


def external_id(payload: dict[str, Any]) -> str:
    return f"claude-code:{payload.get('session_id', 'unknown')}"


def last_assistant_text(transcript_path: str | Path) -> str | None:
    """Return the text of the final assistant message in a Claude Code JSONL transcript."""
    path = Path(transcript_path)
    if not path.is_file():
        return None
    last: str | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = cast("dict[str, Any]", json.loads(line))
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "assistant":
            continue
        message = cast("dict[str, Any]", entry.get("message") or {})
        content = message.get("content")
        if isinstance(content, str):
            text = content
        else:
            parts = [
                str(cast("dict[str, Any]", block).get("text", ""))
                for block in cast("list[Any]", content or [])
                if isinstance(block, dict) and cast("dict[str, Any]", block).get("type") == "text"
            ]
            text = "\n".join(p for p in parts if p)
        if text.strip():
            last = text.strip()
    return last


@dataclass(slots=True)
class HookHandlers:
    services: Services
    space_override: str | None = None
    token_budget: int = 1200

    async def conversation(self, payload: dict[str, Any]) -> Conversation:
        return await self.services.conversations.start(
            NewConversation(
                space=space_for(payload, override=self.space_override),
                agent_id=AGENT_ID,
                external_id=external_id(payload),
                title=str(payload.get("cwd") or ""),
                metadata={"source": payload.get("source", "hook")},
            )
        )

    async def session_start(self, payload: dict[str, Any]) -> dict[str, Any]:
        conversation = await self.conversation(payload)
        context = await self.services.retriever.context(
            RetrievalQuery(
                text=f"project {Path(str(payload.get('cwd') or '')).name} overview",
                space=conversation.space,
                token_budget=self.token_budget,
            )
        )
        text = f"surrealmem: conversation {conversation.id} in space {conversation.space}." + (
            "\n" + context.markdown if not context.is_empty else ""
        )
        return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}

    async def user_prompt_submit(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        prompt = str(payload.get("prompt") or "").strip()
        if not prompt:
            return None
        conversation = await self.conversation(payload)
        context = await self.services.retriever.context(
            RetrievalQuery(
                text=prompt,
                space=conversation.space,
                token_budget=self.token_budget,
                conversation_id=conversation.id,
            )
        )
        await self.services.conversations.append(
            conversation.id, NewMessage(role=Role.USER, content=prompt)
        )
        if context.is_empty:
            return None
        return {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context.markdown,
            }
        }

    async def stop(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if payload.get("stop_hook_active"):
            return None
        transcript = payload.get("transcript_path")
        text = last_assistant_text(str(transcript)) if transcript else None
        if not text:
            return None
        conversation = await self.conversation(payload)
        await self.services.conversations.append(
            conversation.id, NewMessage(role=Role.ASSISTANT, content=text[:20000])
        )
        return None
