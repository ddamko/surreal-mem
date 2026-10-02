/** d3-force-3d wrapper. The scene drives ticks from its own animation frame so there is one clock. */
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, forceZ, type Simulation } from 'd3-force-3d';
import type { SceneLink, SceneNode } from './types';

export class GraphSimulation {
  private readonly sim: Simulation<SceneNode, SceneLink>;
  private dimensions: 2 | 3 = 2;

  constructor() {
    this.sim = forceSimulation<SceneNode, SceneLink>([], 2)
      .alphaMin(0.004)
      .alphaDecay(0.028)
      .velocityDecay(0.35)
      .force('link', forceLink<SceneNode, SceneLink>([]).id((n) => n.id).distance((l) => 26 + l.source.size + l.target.size).strength(0.6))
      .force('charge', forceManyBody<SceneNode>().strength((n) => -40 - n.size * 6).theta(0.9).distanceMax(600))
      .force('collide', forceCollide<SceneNode>((n) => n.size + 3).strength(0.8).iterations(1))
      .force('center', forceCenter<SceneNode>(0, 0, 0).strength(0.05))
      .force('x', forceX<SceneNode>(0).strength(0.015))
      .force('y', forceY<SceneNode>(0).strength(0.015))
      .stop();
  }

  /** Replace the data. `reheat` is the alpha to restart from (0 keeps the layout still). */
  setData(nodes: SceneNode[], links: SceneLink[], reheat: number): void {
    this.sim.nodes(nodes);
    const link = this.sim.force('link') as ReturnType<typeof forceLink<SceneNode, SceneLink>>;
    link.links(links);
    if (reheat > 0) this.sim.alpha(reheat);
  }

  setDimensions(dimensions: 2 | 3): void {
    if (dimensions === this.dimensions) return;
    this.dimensions = dimensions;
    this.sim.numDimensions(dimensions);
    if (dimensions === 3) {
      // Lift nodes off the plane in proportion to the layout's footprint so depth is visible.
      const nodes = this.sim.nodes();
      let minX = Infinity, maxX = -Infinity;
      for (const n of nodes) {
        minX = Math.min(minX, n.x);
        maxX = Math.max(maxX, n.x);
      }
      const spread = Math.max(120, (maxX - minX) * 0.6);
      for (const n of nodes) if (!n.z) n.z = (Math.random() - 0.5) * spread;
      this.sim.force('z', forceZ<SceneNode>(0).strength(0.015));
    } else {
      for (const n of this.sim.nodes()) {
        n.z = 0;
        n.vz = 0;
      }
      this.sim.force('z', null);
    }
    this.sim.alpha(Math.max(this.sim.alpha(), 0.6));
  }

  /** Advance one step when the layout is still settling. Returns whether positions changed. */
  step(): boolean {
    if (!this.active()) return false;
    this.sim.tick();
    if (this.dimensions === 2) for (const n of this.sim.nodes()) n.z = 0;
    return true;
  }

  /** Run synchronous ticks for up to `budgetMs` so a fresh graph is not a blob on first paint. */
  warmUp(budgetMs: number): void {
    const until = performance.now() + budgetMs;
    while (this.active() && performance.now() < until) this.sim.tick();
  }

  active(): boolean {
    return this.sim.alpha() >= this.sim.alphaMin() || this.sim.alphaTarget() > 0;
  }

  reheat(alpha = 1): void {
    this.sim.alpha(alpha);
  }

  dragStart(node: SceneNode): void {
    node.fx = node.x;
    node.fy = node.y;
    this.sim.alphaTarget(0.25).alpha(Math.max(this.sim.alpha(), 0.25));
  }

  drag(node: SceneNode, x: number, y: number): void {
    node.fx = x;
    node.fy = y;
  }

  dragEnd(node: SceneNode): void {
    node.fx = null;
    node.fy = null;
    this.sim.alphaTarget(0);
  }

  nodes(): SceneNode[] {
    return this.sim.nodes();
  }
}
