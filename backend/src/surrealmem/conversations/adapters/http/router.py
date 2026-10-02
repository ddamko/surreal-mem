"""REST routes for conversations and messages."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from surrealmem.conversations.application import (
    AppendMessage,
    CloseConversation,
    GetConversation,
    ListConversations,
    StartConversation,
)
from surrealmem.conversations.domain import Conversation, Message, NewConversation, NewMessage


@dataclass(slots=True)
class ConversationUseCases:
    start: StartConversation
    append: AppendMessage
    get: GetConversation
    list: ListConversations
    close: CloseConversation


def _use_cases(request: Request) -> ConversationUseCases:
    return request.app.state.conversation_use_cases


UseCases = Annotated[ConversationUseCases, Depends(_use_cases)]
router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationDetail(BaseModel):
    conversation: Conversation
    messages: list[Message]


@router.post("", status_code=201)
async def start_conversation(data: NewConversation, uc: UseCases) -> Conversation:
    return await uc.start(data)


@router.get("")
async def list_conversations(
    uc: UseCases,
    space: str | None = None,
    agent_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Conversation]:
    return await uc.list(space=space, agent_id=agent_id, limit=limit, offset=offset)


@router.get("/{conversation_id:path}/messages")
async def list_messages(
    conversation_id: str,
    uc: UseCases,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    before_seq: int | None = None,
) -> list[Message]:
    view = await uc.get(conversation_id, limit=limit, before_seq=before_seq)
    return view.messages


@router.post("/{conversation_id:path}/messages", status_code=201)
async def append_message(conversation_id: str, data: NewMessage, uc: UseCases) -> Message:
    return await uc.append(conversation_id, data)


@router.post("/{conversation_id:path}/close", status_code=204)
async def close_conversation(conversation_id: str, uc: UseCases) -> None:
    await uc.close(conversation_id)


@router.get("/{conversation_id:path}")
async def get_conversation(
    conversation_id: str, uc: UseCases, limit: Annotated[int, Query(ge=1, le=500)] = 100
) -> ConversationDetail:
    view = await uc.get(conversation_id, limit=limit)
    return ConversationDetail(conversation=view.conversation, messages=view.messages)
