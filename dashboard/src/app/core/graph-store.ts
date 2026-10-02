import Graph from 'graphology';
import { themeColor } from './color';
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

/** Build a graphology graph from API rows and size/color nodes by the chosen rules. Layout is the
 *  renderer's job (core/graph-scene). */
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
    });
  }
  for (const edge of edges) {
    if (!graph.hasNode(edge.in) || !graph.hasNode(edge.out)) continue;
    graph.addEdgeWithKey(edge.id, edge.in, edge.out, {
      label: edge.kind,
      kind: edge.kind,
      size: 1 + Math.min(4, Math.log2(1 + (edge.mention_count ?? 1))),
      color: themeColor('--edge-ink', '#667788'),
      confidence: edge.confidence ?? 1,
      proposed: edge.proposed ?? false,
    });
  }
  return graph;
}

export function metricOf(node: GraphNode, sizeBy: SizeBy): number {
  if (sizeBy === 'mention_count') return node.mention_count ?? 0;
  return Number(node.metrics?.[sizeBy] ?? 0);
}

export function communityColor(community: number): string {
  if (community < 0) return themeColor('--edge-ink', '#8a93a8');
  if (community >= COMMUNITY_HUES.length) return '#7a8295';
  return COMMUNITY_HUES[community];
}
