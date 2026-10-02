# surrealmem Claude Code plugin

Gives Claude Code long-term memory (ADR-0027):

- **MCP server** (`.mcp.json`): `surrealmem mcp` over stdio with the memory tools
  (`memory_get_context`, `memory_search`, `memory_store_message`, `memory_add_fact`,
  `memory_add_preference`, `memory_get_entity`, traces, `graph_query`, ...).
- **Hooks** (`hooks/hooks.json`):
  - `SessionStart` opens (or resumes) a conversation keyed by the Claude session id in the space
    `project:<directory name>` and injects an overview of what is already known.
  - `UserPromptSubmit` stores the prompt and injects a budgeted context pack as additional context.
  - `Stop` stores the assistant's final reply from the transcript.

Both read the repository `.env` (SurrealDB URL, inference endpoints). Override the space with
`SURREALMEM_SPACE` or `surrealmem hook --space`.

## Install

```text
claude plugin add /home/derek/code/vibe/surreal-mem/integrations/claude-code   # or: /plugin install from a local marketplace
```

Requirements: `just up` (SurrealDB), `just inference` (embeddings for retrieval), and a running
`just worker` for extraction. Hooks never block: on any failure they log to stderr and exit 0.
