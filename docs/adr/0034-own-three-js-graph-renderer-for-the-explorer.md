# ADR-0034: Our own Three.js renderer for the Graph Explorer

- **Status:** Accepted (supersedes ADR-0019)
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

Sigma.js did the job but looked dated next to the rest of the observatory theme, and the dashboard
already carries Three.js for the Vector Space and the Overview constellation (ADR-0031). Derek asked
for a renderer of our own on Three.js.

## Decision

`dashboard/src/app/core/graph-scene/` is a framework-free renderer the Explorer page drives:

- Nodes are one `THREE.Points` draw with a disc shader (soft centre, faint rim, per-node alpha);
  edges are one `LineSegments` draw with per-vertex colour and alpha. Hover and selection halos are a
  second two-point layer. Both shaders end with Three's colour-space conversion so theme hex colours
  render as authored.
- Layout is d3-force-3d, ticked from the scene's own animation frame (one clock). New graphs warm up
  synchronously for ~160 ms so the first paint is not a blob; expansions keep existing positions and
  spawn new nodes next to a neighbour. Nodes can be dragged in 2D.
- Labels, focused edges, arrowheads and relationship-kind captions are drawn on a 2D canvas overlay
  by a pure, unit-tested placer (priority, then size, collision-free, viewport-clipped). Text stays
  crisp at any zoom and there is no DOM per node.
- 2D is an orthographic camera with cursor-anchored wheel zoom and drag panning; 3D is a perspective
  camera with OrbitControls and depth-faded labels. Switching modes keeps positions and lifts nodes off
  the plane in proportion to the layout's footprint.
- graphology stays as the client-side data model (neighbour and path queries, visible-subgraph
  metrics). `sigma`, `graphology-layout` and `graphology-layout-forceatlas2` are removed.

## Consequences

One visual language across the dashboard and full control over styling and motion. We own picking,
labels and camera code that a library used to provide; the placer and the geometry helpers are
tested, the WebGL path is checked through Playwright screenshots. Performance target is unchanged:
a few thousand visible nodes at 60 fps, with labels capped at 220 per frame.
