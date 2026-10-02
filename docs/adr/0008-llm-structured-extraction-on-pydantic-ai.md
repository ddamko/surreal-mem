# ADR-0008: LLM structured extraction on pydantic-ai

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

GLiNER's general labels do poorly on engineering content, which is half the traffic.

## Decision

One typed extraction call per message window returns entities, relations, facts and preferences validated against pydantic models. Implemented behind an `Extractor` protocol so a GLiNER stage can be added later. Mention offsets are recovered by string matching.

## Consequences

Validated write path end to end; provider choice is configuration.
