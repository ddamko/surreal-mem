/** Public types of the Three.js graph renderer. Framework-free; the Explorer page adapts to it. */
import type { SimulationLink, SimulationNode } from 'd3-force-3d';

export type SceneMode = '2d' | '3d';

export interface GraphInputNode {
  id: string;
  label: string;
  /** Radius in world units (1 world unit = 1 px at zoom 1 in 2D). */
  size: number;
  /** Any CSS color the renderer can resolve to hex (`#rrggbb` preferred). */
  color: string;
}

export interface GraphInputEdge {
  id: string;
  source: string;
  target: string;
  kind: string;
}

export interface GraphInput {
  nodes: GraphInputNode[];
  edges: GraphInputEdge[];
}

export interface SceneNode extends SimulationNode {
  id: string;
  label: string;
  size: number;
  /** Linear-light RGB as Three.js stores it. */
  rgb: [number, number, number];
  x: number;
  y: number;
  z: number;
}

export interface SceneLink extends SimulationLink<SceneNode> {
  id: string;
  source: SceneNode;
  target: SceneNode;
  kind: string;
}

export interface SceneTheme {
  /** Label text color. */
  text: string;
  /** Neutral ink for kind labels and secondary strokes. */
  ink: string;
  /** Page background, used for label halos. */
  background: string;
  /** Accent for the selected node ring and path edges. */
  primary: string;
  font: string;
  mono: string;
}

export interface SceneFocus {
  hovered: string | null;
  selected: string | null;
  pathEdges: ReadonlySet<string>;
}

export interface SceneEvents {
  nodeClick?(id: string): void;
  nodeHover?(id: string | null): void;
  stageClick?(): void;
}
