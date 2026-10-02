import { DatePipe, DecimalPipe, KeyValuePipe } from '@angular/common';
import { Component, effect, inject, resource, signal } from '@angular/core';
import { ApiService } from '../../core/api';
import { LiveService } from '../../core/live';
import { relativeTime } from '../../core/types';
import type { components } from '../../api/schema';

type Job = components['schemas']['Job'];

const KINDS = ['metrics', 'project', 'reflect_sweep', 'salience'] as const;

@Component({
  selector: 'app-operations',
  imports: [DatePipe, DecimalPipe, KeyValuePipe],
  templateUrl: './operations.html',
})
export class OperationsPage {
  private readonly api = inject(ApiService);
  protected readonly live = inject(LiveService);
  protected readonly relativeTime = relativeTime;
  protected readonly kinds = KINDS;
  protected readonly status = signal<string>('');
  protected readonly notice = signal<string | null>(null);

  protected readonly counts = resource({
    loader: async () => (await this.api.client.GET('/api/v1/jobs/counts')).data?.counts ?? {},
  });
  protected readonly jobs = resource({
    params: () => ({ status: this.status() || undefined }),
    loader: async ({ params }) => ((await this.api.client.GET('/api/v1/jobs', { params: { query: { status: params.status, limit: 60 } } })).data ?? []) as Job[],
  });
  protected readonly config = resource({ loader: async () => (await this.api.client.GET('/api/v1/stats/config')).data ?? null });
  protected readonly migrations = resource({ loader: async () => (await this.api.client.GET('/api/v1/stats/migrations')).data ?? [] });

  constructor() {
    let timer: ReturnType<typeof setTimeout> | undefined;
    effect(() => {
      this.live.counter();
      clearTimeout(timer);
      timer = setTimeout(() => {
        this.counts.reload();
        this.jobs.reload();
      }, 2500);
    });
  }

  protected async enqueue(kind: string): Promise<void> {
    const { data, error } = await this.api.client.POST('/api/v1/jobs', { body: { kind, payload: {}, priority: 3 } });
    this.notice.set(error ? `Could not enqueue ${kind}` : `Queued ${kind} (${data?.job_id})`);
    this.counts.reload();
    this.jobs.reload();
  }

  protected workers(): string[] {
    const seen = new Set<string>();
    for (const j of this.jobs.hasValue() ? this.jobs.value() : []) if (j.status === 'running' && j.claimed_by) seen.add(j.claimed_by.split('#')[0]);
    return [...seen];
  }

  protected summary(job: Job): string {
    const r = job.result as Record<string, unknown> | undefined;
    if (job.error) return job.error;
    if (!r) return '';
    if (job.kind === 'extract') return `${r['entities'] ?? 0} entities · ${r['relationships'] ?? 0} relationships · ${r['facts'] ?? 0} facts`;
    return Object.entries(r).filter(([, v]) => typeof v !== 'object').map(([k, v]) => `${k} ${v}`).join(' · ');
  }
}
