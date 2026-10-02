import { DecimalPipe, SlicePipe } from '@angular/common';
import { Component, DestroyRef, ElementRef, afterNextRender, computed, effect, inject, resource, signal, viewChild } from '@angular/core';
import Graph from 'graphology';
import { ApiService } from '../../core/api';
import { themeColor } from '../../core/color';
import { GraphScene } from '../../core/graph-scene/graph-scene';
import type { GraphInput, SceneMode, SceneTheme } from '../../core/graph-scene/types';
import { SpaceService } from '../../core/space';
import { ThemeService } from '../../core/theme';
import { BASE_TYPES, compact, typeColor } from '../../core/types';
import { buildGraph, type ColorBy, type GraphEdge, type GraphNode, type SizeBy } from '../../core/graph-store';

interface Neighborhood {
  entity: GraphNode & { description?: string | null; aliases?: string[]; created_at?: string; first_seen_at?: string | null; archived?: boolean };
  relationships: { id: string; source_id: string; target_id: string; kind: string; confidence: number; mention_count: number; proposed: boolean }[];
  facts: { id: string; statement: string; kind: string; status: string; confidence: number; valid_from?: string | null; recorded_at: string; supersedes?: string | null }[];
  neighbors: GraphNode[];
}

@Component({
  selector: 'app-explorer',
  imports: [DecimalPipe, SlicePipe],
  templateUrl: './explorer.html',
})
export class ExplorerPage {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly space = inject(SpaceService);
  private readonly themeService = inject(ThemeService);
  protected readonly baseTypes = BASE_TYPES;
  protected readonly compact = compact;
  protected readonly typeColor = typeColor;

  private readonly canvas = viewChild.required<ElementRef<HTMLDivElement>>('canvas');
  private scene: GraphScene | null = null;
  private graph: Graph | null = null;

  protected readonly mode = signal<SceneMode>('2d');
  protected readonly enabledTypes = signal<Set<string>>(new Set(BASE_TYPES));
  protected readonly kinds = signal<Set<string>>(new Set());
  protected readonly limit = signal(400);
  protected readonly minMentions = signal(0);
  protected readonly sizeBy = signal<SizeBy>('mention_count');
  protected readonly colorBy = signal<ColorBy>('type');
  protected readonly search = signal('');
  protected readonly selected = signal<string | null>(null);
  protected readonly pathSource = signal<string | null>(null);
  protected readonly pathEdges = signal<Set<string>>(new Set());
  protected readonly hovered = signal<string | null>(null);
  protected readonly status = signal('');

  protected readonly kindOptions = resource({
    loader: async () => {
      const { data } = await this.api.client.GET('/api/v1/relationship-kinds');
      return (data ?? []).filter((k) => k.usage_count > 0).map((k) => k.kind);
    },
  });

  protected readonly graphData = resource({
    params: () => ({
      space: this.space.param(),
      types: [...this.enabledTypes()],
      kinds: [...this.kinds()],
      limit: this.limit(),
      min: this.minMentions(),
    }),
    loader: async ({ params }) => {
      const { data, error } = await this.api.client.GET('/api/v1/graph', {
        params: {
          query: {
            space: params.space,
            base_type: params.types.length === BASE_TYPES.length ? undefined : params.types,
            kind: params.kinds.length ? params.kinds : undefined,
            limit: params.limit,
            min_mentions: params.min,
          },
        },
      });
      if (error) throw error;
      return { nodes: data.nodes as unknown as GraphNode[], edges: data.edges as unknown as GraphEdge[] };
    },
  });

  protected readonly neighborhood = resource({
    params: () => ({ id: this.selected() }),
    loader: async ({ params }) => {
      if (!params.id) return null;
      const { data, error } = await this.api.client.GET('/api/v1/entities/{entity_id}', {
        params: { path: { entity_id: params.id }, query: { hops: 1 } },
      });
      if (error) throw error;
      return data as unknown as Neighborhood;
    },
  });

  protected readonly typeCounts = computed(() => {
    const counts: Record<string, number> = {};
    for (const n of this.graphData.hasValue() ? this.graphData.value().nodes : []) counts[n.base_type] = (counts[n.base_type] ?? 0) + 1;
    return counts;
  });
  protected readonly searchHits = computed(() => {
    const q = this.search().trim().toLowerCase();
    if (!q || !this.graphData.hasValue()) return [];
    return this.graphData.value().nodes.filter((n) => n.name.toLowerCase().includes(q)).slice(0, 8);
  });

  constructor() {
    afterNextRender(() => this.mount());
    effect(() => {
      this.themeService.theme();
      const data = this.graphData.hasValue() ? this.graphData.value() : null;
      const sizeBy = this.sizeBy();
      const colorBy = this.colorBy();
      if (!data) return;
      this.graph = buildGraph(data.nodes, data.edges, { sizeBy, colorBy });
      this.pushGraph();
      this.status.set(`${data.nodes.length} entities · ${data.edges.length} relationships`);
    });
    effect(() => {
      const focus = { hovered: this.hovered(), selected: this.selected(), pathEdges: this.pathEdges() };
      this.scene?.setFocus(focus);
    });
    effect(() => {
      // Read the signal before the optional chain, or the effect never subscribes while the scene is null.
      const mode = this.mode();
      this.scene?.setMode(mode);
    });
  }

  private mount(): void {
    this.scene = new GraphScene(this.canvas().nativeElement, this.sceneTheme(), {
      nodeClick: (id) => this.select(id),
      stageClick: () => this.selected.set(null),
      nodeHover: (id) => this.hovered.set(id),
    });
    this.scene.setMode(this.mode());
    this.pushGraph();
    this.scene.setFocus({ hovered: this.hovered(), selected: this.selected(), pathEdges: this.pathEdges() });
    this.destroyRef.onDestroy(() => {
      this.scene?.dispose();
      this.scene = null;
    });
  }

  private pushGraph(): void {
    if (!this.scene || !this.graph) return;
    const input: GraphInput = {
      nodes: this.graph.mapNodes((id, a) => ({ id, label: String(a['label']), size: Number(a['size']), color: String(a['color']) })),
      edges: this.graph.mapEdges((id, a, source, target) => ({ id, source, target, kind: String(a['kind']) })),
    };
    this.scene.setTheme(this.sceneTheme());
    this.scene.setGraph(input);
  }

  private sceneTheme(): SceneTheme {
    const root = getComputedStyle(document.documentElement);
    return {
      text: themeColor('--color-base-content', '#dddddd'),
      ink: themeColor('--edge-ink', '#8a93a8'),
      background: themeColor('--color-base-100', '#101420'),
      primary: themeColor('--color-primary', '#e8b04b'),
      font: root.getPropertyValue('--font-sans').trim() || 'Inter Variable, sans-serif',
      mono: root.getPropertyValue('--font-mono').trim() || 'JetBrains Mono Variable, monospace',
    };
  }

  protected toggleType(type: string): void {
    const next = new Set(this.enabledTypes());
    if (next.has(type)) next.delete(type);
    else next.add(type);
    if (next.size) this.enabledTypes.set(next);
  }

  protected toggleKind(kind: string): void {
    const next = new Set(this.kinds());
    if (next.has(kind)) next.delete(kind);
    else next.add(kind);
    this.kinds.set(next);
  }

  protected select(id: string): void {
    this.selected.set(id);
    this.search.set('');
    if (this.graph?.hasNode(id)) this.scene?.focusNode(id);
  }

  protected async expand(id: string): Promise<void> {
    if (!this.graph) return;
    const { data } = await this.api.client.GET('/api/v1/graph/neighbors/{entity_id}', { params: { path: { entity_id: id }, query: { hops: 1 } } });
    if (!data) return;
    const current = this.graphData.hasValue() ? this.graphData.value() : { nodes: [], edges: [] };
    const have = new Set(current.nodes.map((n) => n.id));
    const nodes = [...current.nodes, ...(data.nodes as unknown as GraphNode[]).filter((n) => !have.has(n.id))];
    const haveEdges = new Set(current.edges.map((e) => e.id));
    const edges = [...current.edges, ...(data.edges as unknown as GraphEdge[]).filter((e) => !haveEdges.has(e.id))];
    this.graphData.set({ nodes, edges });
  }

  protected async findPath(target: string): Promise<void> {
    const source = this.pathSource();
    if (!source) {
      this.pathSource.set(target);
      this.status.set('Pick a second entity to find the shortest path.');
      return;
    }
    const { data } = await this.api.client.GET('/api/v1/graph/path', { params: { query: { source, target } } });
    this.pathSource.set(null);
    const ids = new Set((data?.edges ?? []).map((e) => String(e['id'])));
    this.pathEdges.set(ids);
    this.status.set(data?.found ? `Path: ${ids.size} hop${ids.size === 1 ? '' : 's'}` : 'No path within 6 hops.');
    if (ids.size) {
      const missing = (data?.edges ?? []).some((e) => !this.graph?.hasEdge(String(e['id'])));
      if (missing) await this.expand(source);
    }
  }

  protected async archive(id: string): Promise<void> {
    await this.api.client.PATCH('/api/v1/entities/{entity_id}', { params: { path: { entity_id: id } }, body: { archived: true } });
    this.selected.set(null);
    this.graphData.reload();
  }

  protected relayout(): void {
    this.scene?.relayout();
  }

  protected fit(): void {
    this.scene?.fit();
  }

  protected nameOf(id: string): string {
    return this.graph?.hasNode(id) ? String(this.graph.getNodeAttribute(id, 'label')) : id;
  }
}
