import { DatePipe } from '@angular/common';
import { Component, computed, inject, resource, signal } from '@angular/core';
import { ApiService } from '../../core/api';
import { SpaceService } from '../../core/space';
import { relativeTime, typeColor } from '../../core/types';
import type { components } from '../../api/schema';

type Conversation = components['schemas']['Conversation'];
type Message = components['schemas']['Message'];
interface Mention { message: string; entity: string; name: string; base_type: string; confidence: number }
interface Fact { id: string; statement: string; kind: string; status: string; sources?: string[] }

@Component({
  selector: 'app-conversations',
  imports: [DatePipe],
  templateUrl: './conversations.html',
})
export class ConversationsPage {
  private readonly api = inject(ApiService);
  protected readonly space = inject(SpaceService);
  protected readonly typeColor = typeColor;
  protected readonly relativeTime = relativeTime;
  protected readonly selected = signal<string | null>(null);
  protected readonly agent = signal<string>('');

  protected readonly list = resource({
    params: () => ({ space: this.space.param(), agent: this.agent() || undefined }),
    loader: async ({ params }) => {
      const { data, error } = await this.api.client.GET('/api/v1/conversations', { params: { query: { space: params.space, agent_id: params.agent, limit: 100 } } });
      if (error) throw error;
      return data as Conversation[];
    },
  });

  protected readonly detail = resource({
    params: () => ({ id: this.selected() }),
    loader: async ({ params }) => {
      if (!params.id) return null;
      const [conv, mentions, traces] = await Promise.all([
        this.api.client.GET('/api/v1/conversations/{conversation_id}', { params: { path: { conversation_id: params.id }, query: { limit: 300 } } }),
        this.api.client.GET('/api/v1/conversations/{conversation_id}/mentions', { params: { path: { conversation_id: params.id } } }),
        this.api.client.GET('/api/v1/traces', { params: { query: { conversation_id: params.id, limit: 20 } } }),
      ]);
      if (conv.error) throw conv.error;
      const byMessage = new Map<string, Mention[]>();
      for (const m of (mentions.data?.rows ?? []) as unknown as Mention[]) {
        const list = byMessage.get(m.message) ?? [];
        list.push(m);
        byMessage.set(m.message, list);
      }
      return { conversation: conv.data.conversation, messages: conv.data.messages as Message[], mentions: byMessage, traces: traces.data ?? [] };
    },
  });

  protected readonly agents = computed(() => {
    const seen = new Set<string>();
    for (const c of this.list.hasValue() ? this.list.value() : []) seen.add(c.agent_id);
    return [...seen].sort();
  });

  protected mentionsFor(id: string): Mention[] {
    return this.detail.hasValue() ? (this.detail.value()?.mentions.get(id) ?? []) : [];
  }

  protected statusBadge(status: string): string {
    return { queued: 'badge-info', running: 'badge-warning', done: 'badge-success', failed: 'badge-error', skipped: 'badge-ghost', pending: 'badge-ghost' }[status] ?? 'badge-ghost';
  }

  protected async wait(messageId: string): Promise<void> {
    const { data } = await this.api.client.GET('/api/v1/jobs', { params: { query: { limit: 200 } } });
    const job = (data ?? []).find((j) => (j.payload as Record<string, unknown>)?.['message_id'] === messageId);
    if (job) await this.api.client.GET('/api/v1/jobs/wait', { params: { query: { job_id: job.id, timeout_seconds: 60 } } });
    this.detail.reload();
  }
}
