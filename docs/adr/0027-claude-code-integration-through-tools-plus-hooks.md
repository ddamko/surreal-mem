# ADR-0027: Claude Code integration through tools plus hooks

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

An MCP server only acts when the model decides to call a tool.

## Decision

The MCP server provides the tools. A plugin under `integrations/claude-code/` adds a `SessionStart` hook that opens a conversation tagged with the project's space, a `UserPromptSubmit` hook that stores the prompt and injects a budgeted context pack, and a `Stop` hook that stores the reply.

## Consequences

Every turn is captured and every prompt gets context; tools remain for deliberate queries and traces.
