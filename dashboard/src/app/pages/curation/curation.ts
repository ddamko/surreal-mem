import { DecimalPipe } from '@angular/common';
import { Component, inject, resource, signal } from '@angular/core';
import { ApiService } from '../../core/api';
import { SpaceService } from '../../core/space';
import { typeColor } from '../../core/types';
import type { components } from '../../api/schema';

type Candidate = components['schemas']['MergeCandidate'];
type Entity = components['schemas']['Entity'];
type Kind = components['schemas']['RelationKind'];

@Component({
  selector: 'app-curation',
  imports: [DecimalPipe],
  templateUrl: './curation.html',
})
export class CurationPage {
  private readonly api = inject(ApiService);
  protected readonly space = inject(SpaceService);
  protected readonly typeColor = typeColor;
  protected readonly busy = signal<string | null>(null);
  protected readonly message = signal<string | null>(null);

  protected readonly candidates = resource({
    loader: async () => {
      const { data, error } = await this.api.client.GET('/api/v1/merge-candidates', { params: { query: { status: 'pending', limit: 100 } } });
      if (error) throw error;
      const list = data as Candidate[];
      const ids = [...new Set(list.flatMap((c) => [c.left_id, c.right_id]))];
      const entities = new Map<string, Entity>();
      await Promise.all(
        ids.map(async (id) => {
          const r = await this.api.client.GET('/api/v1/entities/{entity_id}', { params: { path: { entity_id: id }, query: { hops: 0 } } });
          if (r.data) entities.set(id, r.data.entity as Entity);
        }),
      );
      return list.map((c) => ({ candidate: c, left: entities.get(c.left_id), right: entities.get(c.right_id) }));
    },
  });

  protected readonly kinds = resource({
    loader: async () => {
      const { data, error } = await this.api.client.GET('/api/v1/relationship-kinds');
      if (error) throw error;
      return data as Kind[];
    },
  });

  protected readonly archived = resource({
    params: () => ({ space: this.space.param() }),
    loader: async ({ params }) => {
      const { data, error } = await this.api.client.GET('/api/v1/entities', { params: { query: { space: params.space, include_archived: true, limit: 200 } } });
      if (error) throw error;
      return (data as Entity[]).filter((e) => e.archived && !e.merged_into);
    },
  });

  protected async review(candidate: Candidate, approve: boolean): Promise<void> {
    this.busy.set(candidate.id);
    const { error } = await this.api.client.POST('/api/v1/merge-candidates/{candidate_id}/review', { params: { path: { candidate_id: candidate.id } }, body: { approve, decided_by: 'dashboard' } });
    this.busy.set(null);
    this.message.set(error ? 'Merge failed' : approve ? 'Merged' : 'Kept separate');
    this.candidates.reload();
  }

  protected async swapAndMerge(candidate: Candidate): Promise<void> {
    this.busy.set(candidate.id);
    await this.api.client.POST('/api/v1/entities/{entity_id}/merge', { params: { path: { entity_id: candidate.right_id } }, body: { winner_id: candidate.left_id, reason: 'review' } });
    await this.api.client.POST('/api/v1/merge-candidates/{candidate_id}/review', { params: { path: { candidate_id: candidate.id } }, body: { approve: false, decided_by: 'dashboard' } });
    this.busy.set(null);
    this.candidates.reload();
  }

  protected async decideKind(kind: Kind, proposed: boolean): Promise<void> {
    await this.api.client.POST('/api/v1/relationship-kinds/{kind}', { params: { path: { kind: kind.kind } }, body: { proposed } });
    this.kinds.reload();
  }

  protected async restore(entity: Entity): Promise<void> {
    await this.api.client.PATCH('/api/v1/entities/{entity_id}', { params: { path: { entity_id: entity.id } }, body: { archived: false } });
    this.archived.reload();
  }

  protected proposed(): Kind[] {
    return (this.kinds.hasValue() ? this.kinds.value() : []).filter((k) => k.proposed);
  }
}
