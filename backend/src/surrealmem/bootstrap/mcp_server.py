"""The surrealmem MCP server over stdio (Claude Code) and Streamable HTTP (ADR-0016).

Tools mirror the Neo4j Agent Memory core and extended profiles. The container is resolved lazily
so one server definition serves both the API process (container built in the lifespan) and the
stdio entrypoint.
"""

import asyncio
import re
from collections.abc import Callable
from typing import Any, cast

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from surrealmem.bootstrap.container import AppContainer
from surrealmem.conversations.domain import Conversation, Message, NewConversation, NewMessage, Role
from surrealmem.knowledge.domain import (
    BaseType,
    Entity,
    EntityNeighborhood,
    Fact,
    NewEntity,
    NewFact,
    NewRelationship,
    Relationship,
)
from surrealmem.reasoning.domain import NewStep, NewToolCall, NewTrace, Step, Trace, TraceView
from surrealmem.retrieval.domain import ContextPack, MemoryType, RetrievalQuery, SearchResult
from surrealmem.shared.domain import normalize_name
from surrealmem.shared.infrastructure.surreal.connection import ScriptError, run_one
from surrealmem.shared.infrastructure.surreal.records import plain

INSTRUCTIONS = """\
surrealmem is long-term memory for agents, stored as a knowledge graph in SurrealDB.
Call memory_get_context at the start of a task to recall what is already known about the people,
projects and preferences involved. Store what you learn with memory_store_message (raw turns, which
are extracted in the background) or memory_add_fact / memory_add_preference for things worth keeping
precisely. Memories are scoped by `space` (for example personal, work, project:<name>).
"""

_READ_ONLY = re.compile(r"^\s*(SELECT|RETURN|INFO)\b", re.IGNORECASE)


class StoredMessage(BaseModel):
    conversation: Conversation
    message: Message
    job_id: str | None = Field(default=None, description="Extraction job id, when queued")


class ExportedGraph(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class WaitResult(BaseModel):
    status: str
    result: dict[str, Any] = Field(default_factory=dict[str, Any])
    error: str | None = None


def build_mcp_server(
    get_container: Callable[[], AppContainer],
    *,
    default_space: str,
    default_agent_id: str,
    default_user_name: str,
) -> MCPServer:
    mcp = MCPServer("surrealmem", instructions=INSTRUCTIONS)

    def services():
        return get_container().services

    def space_of(value: str | None) -> str:
        return value or default_space

    def agent_of(value: str | None) -> str:
        return value or default_agent_id

    async def resolve_entity(name_or_id: str, base_type: BaseType | None = None) -> Entity | None:
        k = services().knowledge
        if name_or_id.startswith("entity:"):
            return await k.entities.get(name_or_id)
        key = normalize_name(name_or_id)
        types = [base_type] if base_type else list(BaseType)
        for candidate in types:
            found = await k.entities.find_exact(candidate, key)
            if found is None:
                found = await k.entities.find_by_alias(candidate, key)
            if found is not None:
                return found
        hits = await k.entities.search_text(name_or_id, base_type=base_type, limit=1)
        return hits[0].entity if hits else None

    async def ensure_entity(name: str, base_type: str | None, space: str) -> Entity:
        typed = BaseType(base_type) if base_type else None
        found = await resolve_entity(name, typed)
        if found is not None:
            return found
        entity, _ = await services().knowledge.upsert_entity(
            NewEntity(name=name, base_type=typed or BaseType.CONCEPT, space=space)
        )
        return entity

    # ------------------------------------------------------------------ short-term

    @mcp.tool()
    async def memory_store_message(
        content: str,
        role: str = "user",
        conversation_id: str | None = None,
        space: str | None = None,
        agent_id: str | None = None,
        external_id: str | None = None,
        extract: bool = True,
    ) -> StoredMessage:
        """Store one conversation turn. Entities, relationships and facts are extracted from it in
        the background. Pass conversation_id to continue a conversation, or external_id (for example
        a session id) to let the server find or create one."""
        s = services()
        conversation = None
        if conversation_id:
            conversation = await s.conversations.repository.get(conversation_id)
            if conversation is None:
                raise ToolError(f"conversation not found: {conversation_id}")
        if conversation is None:
            conversation = await s.conversations.start(
                NewConversation(
                    space=space_of(space), agent_id=agent_of(agent_id), external_id=external_id
                )
            )
        message = (
            await s.conversations.append(
                conversation.id, NewMessage(role=Role(role), content=content)
            )
            if extract
            else await s.conversations.repository.append_message(
                conversation.id, NewMessage(role=Role(role), content=content)
            )
        )
        job_id = None
        if message.extraction_status.value == "queued":
            jobs = await s.extraction.job_store.recent(limit=5, status="queued")
            job_id = next((j.id for j in jobs if j.payload.get("message_id") == message.id), None)
        return StoredMessage(conversation=conversation, message=message, job_id=job_id)

    @mcp.tool()
    async def memory_get_conversation(conversation_id: str, limit: int = 50) -> list[Message]:
        """Return the messages of a conversation in order."""
        view = await services().conversations.get(conversation_id, limit=limit)
        return view.messages

    @mcp.tool()
    async def memory_list_conversations(
        space: str | None = None, agent_id: str | None = None, limit: int = 20
    ) -> list[Conversation]:
        """List recent conversations, optionally filtered by space and agent."""
        return await services().conversations.list(space=space, agent_id=agent_id, limit=limit)

    # ------------------------------------------------------------------ retrieval

    @mcp.tool()
    async def memory_get_context(
        query: str,
        space: str | None = None,
        token_budget: int = 1500,
        conversation_id: str | None = None,
        extra_spaces: list[str] | None = None,
    ) -> ContextPack:
        """Assemble the memories relevant to a query (preferences, facts, entities, summaries,
        messages) within a token budget, with a ready-to-paste markdown block."""
        return await services().retriever.context(
            RetrievalQuery(
                text=query,
                space=space_of(space),
                token_budget=token_budget,
                conversation_id=conversation_id,
                extra_spaces=extra_spaces or [],
            )
        )

    @mcp.tool()
    async def memory_search(
        query: str,
        space: str | None = None,
        limit: int = 10,
        memory_types: list[str] | None = None,
        extra_spaces: list[str] | None = None,
    ) -> SearchResult:
        """Hybrid search (BM25 + vectors + graph expansion) across memory types, with per-item
        score breakdowns. memory_types: fact, entity, message, summary, observation, trace."""
        types = [MemoryType(t) for t in memory_types] if memory_types else None
        kwargs: dict[str, Any] = {}
        if types:
            kwargs["memory_types"] = types
        return await services().retriever.search(
            RetrievalQuery(
                text=query,
                space=space_of(space),
                limit=limit,
                extra_spaces=extra_spaces or [],
                **kwargs,
            )
        )

    # ------------------------------------------------------------------ long-term

    @mcp.tool()
    async def memory_add_entity(
        name: str,
        entity_type: str,
        subtype: str | None = None,
        description: str | None = None,
        aliases: list[str] | None = None,
        space: str | None = None,
    ) -> Entity:
        """Create or update an entity. entity_type is one of person, organization, location, event,
        object, concept; subtype is free snake_case (git_repository, city, software_library)."""
        try:
            typed = BaseType(entity_type)
        except ValueError as exc:
            raise ToolError(f"entity_type must be one of {[t.value for t in BaseType]}") from exc
        entity, _ = await services().knowledge.upsert_entity(
            NewEntity(
                name=name,
                base_type=typed,
                subtype=subtype,
                description=description,
                aliases=aliases or [],
                space=space_of(space),
            )
        )
        return entity

    @mcp.tool()
    async def memory_get_entity(name_or_id: str, hops: int = 1) -> EntityNeighborhood:
        """Look up an entity by name, alias or id and return its relationships, facts and the
        entities within `hops` hops."""
        entity = await resolve_entity(name_or_id)
        if entity is None:
            raise ToolError(f"no entity matches {name_or_id!r}")
        return await services().knowledge.get_entity(entity.id, hops=hops)

    @mcp.tool()
    async def memory_create_relationship(
        source: str,
        kind: str,
        target: str,
        source_type: str | None = None,
        target_type: str | None = None,
        confidence: float = 1.0,
        space: str | None = None,
    ) -> Relationship:
        """Create a typed relationship between two entities named by name or id (UPPER_SNAKE_CASE
        kind such as WORKS_AT, USES, LIVES_IN). Unknown entities are created."""
        sp = space_of(space)
        src = await ensure_entity(source, source_type, sp)
        dst = await ensure_entity(target, target_type, sp)
        return await services().knowledge.add_relationship(
            NewRelationship(
                source_id=src.id, target_id=dst.id, kind=kind, confidence=confidence, space=sp
            )
        )

    @mcp.tool()
    async def memory_add_fact(
        statement: str,
        subject: str,
        kind: str,
        object: str | None = None,
        object_literal: str | None = None,
        subject_type: str | None = None,
        object_type: str | None = None,
        category: str | None = None,
        confidence: float = 1.0,
        valid_from: str | None = None,
        valid_to: str | None = None,
        space: str | None = None,
    ) -> Fact:
        """Store a fact about a subject entity: a self-contained statement plus a predicate kind,
        with an entity object or a literal value and optional ISO validity dates. Functional kinds
        (LIVES_IN, HAS_ROLE, REPORTS_TO, ...) supersede the previous value."""
        from surrealmem.extraction.application import parse_date

        sp = space_of(space)
        subj = await ensure_entity(subject, subject_type, sp)
        obj = await ensure_entity(object, object_type, sp) if object else None
        return await services().knowledge.add_fact(
            NewFact(
                statement=statement,
                space=sp,
                subject_id=subj.id,
                kind=kind,
                object_id=obj.id if obj else None,
                object_literal=object_literal,
                category=category,
                confidence=confidence,
                valid_from=parse_date(valid_from),
                valid_to=parse_date(valid_to),
                source_kind="agent",  # pyright: ignore[reportArgumentType]
            )
        )

    @mcp.tool()
    async def memory_add_preference(
        preference: str,
        category: str,
        subject: str | None = None,
        space: str | None = None,
        confidence: float = 1.0,
    ) -> Fact:
        """Record a preference ("prefers tabs", category "indentation"). A newer preference in the
        same category supersedes the older one. subject defaults to the user."""
        sp = space_of(space)
        subj = await ensure_entity(subject or default_user_name, "person", sp)
        return await services().knowledge.add_fact(
            NewFact(
                statement=f"{subj.name} prefers {preference}.",
                space=sp,
                subject_id=subj.id,
                kind="PREFERS",
                object_literal=preference,
                category=category,
                confidence=confidence,
                source_kind="agent",  # pyright: ignore[reportArgumentType]
            )
        )

    @mcp.tool()
    async def memory_export_graph(space: str | None = None, limit: int = 200) -> ExportedGraph:
        """Export entities and relationships (optionally within a space) as nodes and edges."""
        k = services().knowledge
        entities = await k.entities.list(space=space, limit=limit)
        ids = [e.id for e in entities]
        edges = await k.relationships.among(ids)
        return ExportedGraph(
            nodes=[e.model_dump(mode="json", exclude={"metadata"}) for e in entities],
            edges=[r.model_dump(mode="json", exclude={"metadata"}) for r in edges],
        )

    # ------------------------------------------------------------------ reasoning

    @mcp.tool()
    async def memory_start_trace(
        task: str,
        space: str | None = None,
        agent_id: str | None = None,
        conversation_id: str | None = None,
        message_id: str | None = None,
    ) -> Trace:
        """Begin recording a reasoning trace for a task."""
        return await services().reasoning.start(
            NewTrace(
                space=space_of(space),
                agent_id=agent_of(agent_id),
                task=task,
                conversation_id=conversation_id,
                message_id=message_id,
            )
        )

    @mcp.tool()
    async def memory_record_step(
        trace_id: str,
        thought: str | None = None,
        action: str | None = None,
        observation: str | None = None,
        tool: str | None = None,
        tool_arguments: dict[str, Any] | None = None,
        tool_result: str | None = None,
        touched: list[str] | None = None,
    ) -> Step:
        """Add a step to a trace, optionally with one tool call and the entities (names or ids) it
        touched."""
        touched_ids: list[str] = []
        for name in touched or []:
            entity = await resolve_entity(name)
            if entity is not None:
                touched_ids.append(entity.id)
        calls = (
            [NewToolCall(tool=tool, arguments=tool_arguments or {}, result=tool_result)]
            if tool
            else []
        )
        return await services().reasoning.record(
            trace_id,
            NewStep(
                thought=thought,
                action=action,
                observation=observation,
                tool_calls=calls,
                touched_entity_ids=touched_ids,
            ),
        )

    @mcp.tool()
    async def memory_complete_trace(
        trace_id: str, outcome: str | None = None, success: bool | None = None
    ) -> Trace:
        """Finish a trace with its outcome."""
        return await services().reasoning.complete(trace_id, outcome=outcome, success=success)

    @mcp.tool()
    async def memory_get_trace(trace_id: str) -> TraceView:
        """Return a trace with its steps and tool calls."""
        return await services().reasoning.get(trace_id)

    # ------------------------------------------------------------------ operations

    @mcp.tool()
    async def memory_wait_for_extraction(job_id: str, timeout_seconds: float = 30) -> WaitResult:
        """Block until an extraction job finishes (or the timeout passes) and report its result."""
        store = services().extraction.job_store
        deadline = asyncio.get_running_loop().time() + max(0.0, min(timeout_seconds, 300))
        while True:
            job = await store.get(job_id)
            if job is None:
                raise ToolError(f"job not found: {job_id}")
            if job.status.value in ("done", "dead"):
                return WaitResult(status=job.status.value, result=job.result, error=job.error)
            if asyncio.get_running_loop().time() >= deadline:
                return WaitResult(status=job.status.value, result=job.result, error=job.error)
            await asyncio.sleep(0.25)

    @mcp.tool()
    async def graph_query(query: str) -> list[Any]:
        """Run a read-only SurrealQL statement (SELECT, RETURN or INFO) against the memory graph.
        Tables: entity, related_to, fact, alias, conversation, message, trace, step, tool_call,
        summary, observation, job."""
        statement = query.strip().rstrip(";")
        if ";" in statement or not _READ_ONLY.match(statement):
            raise ToolError("only a single SELECT, RETURN or INFO statement is allowed")
        try:
            result = await run_one(get_container().db, statement)
        except ScriptError as exc:
            raise ToolError(str(exc)) from exc
        rows = cast("list[Any]", result if isinstance(result, list) else [result])
        return [plain(r) for r in rows]

    # ------------------------------------------------------------------ resources and prompts

    @mcp.resource("memory://graph/stats")
    async def graph_stats() -> dict[str, Any]:
        """Counts of entities by type, facts by status and jobs by status."""
        s = services()
        return {
            "entities_by_type": await s.knowledge.entities.count_by_type(),
            "facts_by_status": await s.knowledge.facts.count_by_status(),
            "jobs_by_status": await s.extraction.job_store.counts(),
        }

    @mcp.resource("memory://entities")
    async def entity_catalog() -> str:
        """The most mentioned entities, one per line."""
        entities = await services().knowledge.entities.list(limit=200)
        return "\n".join(f"{e.name} ({e.base_type.value}) x{e.mention_count}" for e in entities)

    @mcp.resource("memory://context/{conversation_id}")
    async def conversation_context(conversation_id: str) -> str:
        """Recent messages of a conversation."""
        view = await services().conversations.get(conversation_id, limit=30)
        return "\n".join(f"[{m.role.value}] {m.content}" for m in view.messages)

    @mcp.prompt()
    def memory_conversation(space: str | None = None) -> str:
        """How to use surrealmem during a conversation."""
        return (
            f"You have long-term memory in surrealmem (space: {space_of(space)}). Before answering "
            "questions about people, projects, preferences or past decisions, call "
            "memory_get_context with the user's request. After learning something durable, call "
            "memory_add_fact or memory_add_preference. Store raw turns with memory_store_message."
        )

    @mcp.prompt()
    def memory_review(entity: str) -> str:
        """Review what is known about an entity and flag contradictions."""
        return (
            f"Call memory_get_entity for {entity!r} with hops=2, list its active facts in time "
            "order, point out facts that contradict each other or look stale, and propose which "
            "to invalidate."
        )

    return mcp
