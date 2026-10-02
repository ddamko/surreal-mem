# ADR-0031: Three.js for the 3D vector space and the live constellation

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

Three.js excels at volumetric animated scenes and is weaker than Sigma for dense labeled exploration.

## Decision

Use Three.js 0.186 directly (the Angular wrapper lags behind) for a 3D embedding map with instanced points, orbit controls and cluster hulls, and for a live memory constellation on the Overview fed by the WebSocket relay. The Explorer keeps Sigma, with an optional 3D view of its current subgraph.

*Amendment 2026-10-02:* the Explorer now has its own Three.js renderer with a 2D/3D toggle (ADR-0034).

## Consequences

Depth carries information where it helps; precision views stay 2D.
