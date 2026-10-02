/** Minimal typings for d3-force-3d (d3-force with 1–3 dimensions). Only what graph-scene uses. */
declare module 'd3-force-3d' {
  export interface SimulationNode {
    index?: number;
    x?: number;
    y?: number;
    z?: number;
    vx?: number;
    vy?: number;
    vz?: number;
    fx?: number | null;
    fy?: number | null;
    fz?: number | null;
  }

  export interface SimulationLink<N extends SimulationNode> {
    source: N | string | number;
    target: N | string | number;
    index?: number;
  }

  export interface Force<N extends SimulationNode> {
    (alpha: number): void;
    initialize?(nodes: N[], random: () => number, numDimensions: number): void;
  }

  export interface Simulation<N extends SimulationNode, L extends SimulationLink<N>> {
    restart(): this;
    stop(): this;
    tick(iterations?: number): this;
    nodes(): N[];
    nodes(nodes: N[]): this;
    alpha(): number;
    alpha(alpha: number): this;
    alphaMin(): number;
    alphaMin(min: number): this;
    alphaDecay(): number;
    alphaDecay(decay: number): this;
    alphaTarget(): number;
    alphaTarget(target: number): this;
    velocityDecay(): number;
    velocityDecay(decay: number): this;
    numDimensions(): number;
    numDimensions(dimensions: 1 | 2 | 3): this;
    force(name: string): Force<N> | undefined;
    force(name: string, force: Force<N> | null): this;
    find(x: number, y: number, z?: number, radius?: number): N | undefined;
    on(typenames: string, listener: ((this: Simulation<N, L>) => void) | null): this;
  }

  export interface ForceLink<N extends SimulationNode, L extends SimulationLink<N>> extends Force<N> {
    links(): L[];
    links(links: L[]): this;
    id(accessor: (node: N, i: number, nodes: N[]) => string | number): this;
    distance(distance: number | ((link: L, i: number, links: L[]) => number)): this;
    strength(strength: number | ((link: L, i: number, links: L[]) => number)): this;
    iterations(iterations: number): this;
  }

  export interface ForceManyBody<N extends SimulationNode> extends Force<N> {
    strength(strength: number | ((node: N, i: number, nodes: N[]) => number)): this;
    theta(theta: number): this;
    distanceMin(distance: number): this;
    distanceMax(distance: number): this;
  }

  export interface ForceCollide<N extends SimulationNode> extends Force<N> {
    radius(radius: number | ((node: N, i: number, nodes: N[]) => number)): this;
    strength(strength: number): this;
    iterations(iterations: number): this;
  }

  export interface ForceCenter<N extends SimulationNode> extends Force<N> {
    strength(strength: number): this;
  }

  export interface ForceAxis<N extends SimulationNode> extends Force<N> {
    strength(strength: number | ((node: N, i: number, nodes: N[]) => number)): this;
  }

  export function forceSimulation<N extends SimulationNode, L extends SimulationLink<N> = SimulationLink<N>>(
    nodes?: N[],
    numDimensions?: 1 | 2 | 3,
  ): Simulation<N, L>;
  export function forceLink<N extends SimulationNode, L extends SimulationLink<N>>(links?: L[]): ForceLink<N, L>;
  export function forceManyBody<N extends SimulationNode>(): ForceManyBody<N>;
  export function forceCollide<N extends SimulationNode>(radius?: number | ((node: N) => number)): ForceCollide<N>;
  export function forceCenter<N extends SimulationNode>(x?: number, y?: number, z?: number): ForceCenter<N>;
  export function forceX<N extends SimulationNode>(x?: number): ForceAxis<N>;
  export function forceY<N extends SimulationNode>(y?: number): ForceAxis<N>;
  export function forceZ<N extends SimulationNode>(z?: number): ForceAxis<N>;
}
