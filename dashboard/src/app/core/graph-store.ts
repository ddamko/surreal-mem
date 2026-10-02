import Graph from 'graphology';
import forceAtlas2 from 'graphology-layout-forceatlas2';
import { circular } from 'graphology-layout';
import { typeColor } from './types';

export interface GraphNode {
  id: string;
  name: string;
  base_type: string;
  subtype?: string | null;
  mention_count?: number;
  salience?: number;
  metrics?: Record<string, number>;
  spaces?: string[];
}

export interface GraphEdge {
  id: string;
  in: string;
  out: string;
  kind: string;
  confidence?: number;
  mention_count?: number;
  proposed?: boolean;
}

export type SizeBy = 'mention_count' | 'pagerank' | 'degree' | 'betweenness';
export type ColorBy = 'type' | 'community';

const COMMUNITY_HUES = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#9085e9', '#008300', '#e66767'];

/** Build a graphology graph from API rows, lay it out, and size/color nodes by the chosen rules. */
export function buildGraph(nodes: GraphNode[], edges: GraphEdge[], options: { sizeBy: SizeBy; colorBy: ColorBy }): Graph {
  const graph = new Graph({ multi: true, type: 'directed' });
  const values = nodes.map((n) => metricOf(n, options.sizeBy));
  const max = Math.max(1e-9, ...values);
  const min = Math.min(...values, 0);
  for (const node of nodes) {
    const value = metricOf(node, options.sizeBy);
    const scaled = max === min ? 0.5 : (value - min) / (max - min);
    const community = node.metrics?.['community'] ?? -1;
    graph.addNode(node.id, {
      label: node.name,
      size: 3 + Math.sqrt(scaled) * 14,
      color: options.colorBy === 'community' ? communityColor(community) : typeColor(node.base_type),
      base_type: node.base_type,
      subtype: node.subtype ?? null,
      mention_count: node.mention_count ?? 0,
      community,
      metrics: node.metrics ?? {},
      x: Math.random(),
      y: Math.random(),
    });
  }
  for (const edge of edges) {
    if (!graph.hasNode(edge.in) || !graph.hasNode(edge.out)) continue;
    graph.addEdgeWithKey(edge.id, edge.in, edge.out, {
      label: edge.kind,
      kind: edge.kind,
      size: 1 + Math.min(4, Math.log2(1 + (edge.mention_count ?? 1))),
      color: 'var(--edge-ink)',
      confidence: edge.confidence ?? 1,
      proposed: edge.proposed ?? false,
      type: 'arrow',
    });
  }
  layout(graph);
  return graph;
}

export function layout(graph: Graph): void {
  if (graph.order === 0) return;
  circular.assign(graph, { scale: 100 });
  const settings = forceAtlas2.inferSettings(graph);
  forceAtlas2.assign(graph, { iterations: graph.order > 800 ? 120 : 300, settings: { ...settings, gravity: 1, scalingRatio: 8, barnesHutOptimize: graph.order > 400 } });
}

export function metricOf(node: GraphNode, sizeBy: SizeBy): number {
  if (sizeBy === 'mention_count') return node.mention_count ?? 0;
  return Number(node.metrics?.[sizeBy] ?? 0);
}

export function communityColor(community: number): string {
  if (community < 0) return 'var(--edge-ink)';
  if (community >= COMMUNITY_HUES.length) return '#7a8295';
  return COMMUNITY_HUES[community];
}
