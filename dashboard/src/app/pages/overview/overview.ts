import { Component, computed, effect, inject, resource } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/api';
import { LiveService } from '../../core/live';
import { SpaceService } from '../../core/space';
import { compact, relativeTime, shortId } from '../../core/types';
import { TimelineChart } from './timeline-chart';
import { Constellation } from './constellation';

@Component({
  selector: 'app-overview',
  imports: [RouterLink, TimelineChart, Constellation],
  templateUrl: './overview.html',
})
export class OverviewPage {
  private readonly api = inject(ApiService);
  protected readonly live = inject(LiveService);
  protected readonly space = inject(SpaceService);
  protected readonly compact = compact;
  protected readonly relativeTime = relativeTime;
  protected readonly shortId = shortId;

  protected readonly overview = this.space.overview;
  protected readonly timeline = resource({
    params: () => ({ space: this.space.param() }),
    loader: async ({ params }) => {
      const { data, error } = await this.api.client.GET('/api/v1/stats/timeline', {
        params: { query: { space: params.space, days: 30 } },
      });
      if (error) throw error;
      return data.series as Record<string, { day: string; n: number }[]>;
    },
  });
  protected readonly facts = resource({
    params: () => ({ space: this.space.param() }),
    loader: async ({ params }) => {
      const { data, error } = await this.api.client.GET('/api/v1/analytics/facts', {
        params: { query: { space: params.space } },
      });
      if (error) throw error;
      return data as {
        by_status: Record<string, number>;
        flagged: number;
        contradictions: unknown[];
      };
    },
  });

  protected readonly tiles = computed(() => {
    const o = this.overview.hasValue() ? this.overview.value() : undefined;
    const f = this.facts.hasValue() ? this.facts.value() : undefined;
    if (!o) return [];
    return [
      { label: 'Entities', value: o.tables['entity'] ?? 0, note: Object.entries(o.entities_by_type ?? {}).map(([t, n]) => `${n} ${t}`).join(' · ') },
      { label: 'Relationships', value: o.tables['related_to'] ?? 0, note: `${(o.relationship_kinds ?? []).length} kinds in use` },
      { label: 'Active facts', value: f?.by_status['active'] ?? o.facts_by_status['active'] ?? 0, note: `${f?.by_status['invalidated'] ?? 0} superseded · ${f?.flagged ?? 0} flagged` },
      { label: 'Messages', value: o.tables['message'] ?? 0, note: `${o.tables['conversation'] ?? 0} conversations` },
      { label: 'Jobs queued', value: o.jobs_by_status['queued'] ?? 0, note: `${o.jobs_by_status['running'] ?? 0} running · ${o.jobs_by_status['dead'] ?? 0} dead` },
      { label: 'Merge reviews', value: o.tables['merge_candidate'] ?? 0, note: 'pending candidates' },
    ];
  });

  protected readonly recent = computed(() =>
    this.live.feed().filter((e) => ['entity', 'fact', 'related_to', 'job', 'merge_candidate'].includes(e.table)).slice(0, 14),
  );

  constructor() {
    // Refresh counts when writes arrive, but not more than every few seconds.
    let timer: ReturnType<typeof setTimeout> | undefined;
    effect(() => {
      this.live.counter();
      clearTimeout(timer);
      timer = setTimeout(() => {
        this.overview.reload();
        this.facts.reload();
      }, 4000);
    });
  }

  protected describe(event: { table: string; action: string; record: Record<string, unknown> }): string {
    const r = event.record;
    switch (event.table) {
      case 'entity':
        return `${event.action === 'CREATE' ? 'New' : 'Updated'} ${r['base_type'] ?? 'entity'}: ${r['name'] ?? ''}`;
      case 'fact':
        return `${r['status'] === 'invalidated' ? 'Superseded' : event.action === 'CREATE' ? 'New fact' : 'Fact'}: ${String(r['statement'] ?? '').slice(0, 90)}`;
      case 'related_to':
        return `Edge ${r['kind'] ?? ''}`;
      case 'job':
        return `Job ${r['kind'] ?? ''} ${r['status'] ?? ''}`;
      case 'merge_candidate':
        return `Merge candidate (${Number(r['score'] ?? 0).toFixed(2)})`;
      default:
        return `${event.table} ${event.action.toLowerCase()}`;
    }
  }
}
