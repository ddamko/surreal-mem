import { DecimalPipe } from '@angular/common';
import { Component, computed, effect, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api';
import { SpaceService } from '../../core/space';
import { typeColor } from '../../core/types';
import type { components } from '../../api/schema';

type ApiPack = components['schemas']['ContextPack'];
type ApiSearch = components['schemas']['SearchResult'];
type ApiItem = components['schemas']['RetrievedItem'];

export interface Score {
  rrf: number;
  graph: number;
  recency: number;
  salience: number;
  confidence: number;
  final: number;
  lexical_rank: number | null;
  vector_rank: number | null;
  vector_similarity: number | null;
}
export interface Item {
  id: string;
  type: string;
  text: string;
  via: string[];
  score: Score;
}
export interface Linked {
  id: string;
  name: string;
  base_type: string;
  score: number;
  matched_on: string;
}
export interface Pack {
  preferences: Item[];
  facts: Item[];
  entities: Item[];
  summaries: Item[];
  observations: Item[];
  messages: Item[];
  linked: Linked[];
  graphEntities: number;
  graphRelationships: number;
  warnings: string[];
  markdown: string;
  tokens_used: number;
  token_budget: number;
  dropped: number;
  timings_ms: Record<string, number>;
}
export interface SearchResult {
  items: Item[];
  linked: Linked[];
  warnings: string[];
  timings_ms: Record<string, number>;
}

function item(raw: ApiItem): Item {
  const s: Partial<NonNullable<ApiItem['score']>> = raw.score ?? {};
  return {
    id: raw.id,
    type: raw.type,
    text: raw.text,
    via: raw.via ?? [],
    score: {
      rrf: s.rrf ?? 0,
      graph: s.graph ?? 0,
      recency: s.recency ?? 0,
      salience: s.salience ?? 0,
      confidence: s.confidence ?? 0,
      final: s.final ?? 0,
      lexical_rank: s.lexical_rank ?? null,
      vector_rank: s.vector_rank ?? null,
      vector_similarity: s.vector_similarity ?? null,
    },
  };
}

function pack(raw: ApiPack): Pack {
  return {
    preferences: (raw.preferences ?? []).map(item),
    facts: (raw.facts ?? []).map(item),
    entities: (raw.entities ?? []).map(item),
    summaries: (raw.summaries ?? []).map(item),
    observations: (raw.observations ?? []).map(item),
    messages: (raw.messages ?? []).map(item),
    linked: (raw.graph?.linked ?? []) as Linked[],
    graphEntities: raw.graph?.entities?.length ?? 0,
    graphRelationships: raw.graph?.relationships?.length ?? 0,
    warnings: raw.warnings ?? [],
    markdown: raw.markdown,
    tokens_used: raw.tokens_used,
    token_budget: raw.token_budget,
    dropped: raw.dropped ?? 0,
    timings_ms: (raw.timings_ms ?? {}) as Record<string, number>,
  };
}

function search(raw: ApiSearch): SearchResult {
  return {
    items: raw.items.map(item),
    linked: (raw.graph?.linked ?? []) as Linked[],
    warnings: raw.warnings ?? [],
    timings_ms: (raw.timings_ms ?? {}) as Record<string, number>,
  };
}

@Component({
  selector: 'app-playground',
  imports: [DecimalPipe],
  templateUrl: './playground.html',
})
export class PlaygroundPage {
  private readonly api = inject(ApiService);
  protected readonly space = inject(SpaceService);
  protected readonly typeColor = typeColor;

  protected readonly query = signal('');
  protected readonly budget = signal(1500);
  protected readonly hops = signal(1);
  protected readonly limit = signal(20);
  protected readonly lexical = signal(true);
  protected readonly vector = signal(true);
  protected readonly graph = signal(true);
  protected readonly includeShared = signal(true);
  /** Spaces to retrieve from. Follows the sidebar selection (one space, or all when "All spaces"),
   *  and can then be widened or narrowed here. `shared` is governed by the toggle below. */
  protected readonly chosenSpaces = signal<Set<string>>(new Set());
  protected readonly spaceOptions = computed(() => this.space.spaces().filter((s) => s !== 'shared'));
  protected readonly mode = signal<'context' | 'search'>('context');
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly pack = signal<Pack | null>(null);
  protected readonly result = signal<SearchResult | null>(null);
  protected readonly history = signal<string[]>([]);

  constructor() {
    effect(() => {
      const selected = this.space.selected();
      const options = this.spaceOptions();
      this.chosenSpaces.set(new Set(selected ? [selected] : options));
    });
  }

  protected toggleSpace(name: string): void {
    const next = new Set(this.chosenSpaces());
    if (next.has(name)) next.delete(name);
    else next.add(name);
    this.chosenSpaces.set(next);
  }

  protected chooseAllSpaces(all: boolean): void {
    this.chosenSpaces.set(new Set(all ? this.spaceOptions() : []));
  }

  protected readonly sections = computed(() => {
    const p = this.pack();
    if (!p) return [];
    return [
      { title: 'Preferences', items: p.preferences },
      { title: 'Facts', items: p.facts },
      { title: 'Entities', items: p.entities },
      { title: 'Summaries', items: p.summaries },
      { title: 'Observations', items: p.observations },
      { title: 'Messages', items: p.messages },
    ].filter((s) => s.items.length);
  });

  protected async run(): Promise<void> {
    const text = this.query().trim();
    if (!text) return;
    const spaces = [...this.chosenSpaces()];
    if (!spaces.length && !this.includeShared()) {
      this.error.set('Pick at least one space.');
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    const [first = 'shared', ...rest] = spaces;
    const body = {
      text,
      space: first,
      extra_spaces: rest,
      include_shared: this.includeShared(),
      token_budget: this.budget(),
      hops: this.hops(),
      limit: this.limit(),
      lexical: this.lexical(),
      vector: this.vector(),
      graph: this.graph(),
    };
    try {
      if (this.mode() === 'context') {
        const { data, error } = await this.api.client.POST('/api/v1/retrieval/context', { body });
        if (error) throw error;
        this.pack.set(pack(data));
        this.result.set(null);
      } else {
        const { data, error } = await this.api.client.POST('/api/v1/retrieval/search', { body });
        if (error) throw error;
        this.result.set(search(data));
        this.pack.set(null);
      }
      this.history.update((h) => [text, ...h.filter((q) => q !== text)].slice(0, 8));
    } catch (e) {
      const problem = typeof e === 'object' && e ? (e as { detail?: unknown; title?: unknown; status?: unknown }) : {};
      this.error.set(problem.detail ? String(problem.detail) : problem.title ? `${problem.status ?? ''} ${problem.title}`.trim() : 'Request failed');
    } finally {
      this.busy.set(false);
    }
  }

  protected scoreBars(item: Item): { label: string; value: number }[] {
    const s = item.score;
    return [
      { label: 'rrf', value: s.rrf },
      { label: 'graph', value: s.graph },
      { label: 'recency', value: s.recency },
      { label: 'salience', value: s.salience },
      { label: 'confidence', value: s.confidence },
    ];
  }

  protected copyMarkdown(): void {
    const md = this.pack()?.markdown;
    if (md) void navigator.clipboard?.writeText(md);
  }

  protected timings(): { k: string; v: number }[] {
    const t = (this.pack()?.timings_ms ?? this.result()?.timings_ms ?? {}) as Record<string, number>;
    return Object.entries(t).map(([k, v]) => ({ k, v }));
  }
}
