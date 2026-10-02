import { Injectable, computed, inject, resource, signal } from '@angular/core';
import { ApiService } from './api';

const SPACE_KEY = 'surrealmem.space';

/** The selected space scopes every page (ADR-0002). Empty string means "all spaces". */
@Injectable({ providedIn: 'root' })
export class SpaceService {
  private readonly api = inject(ApiService);
  readonly selected = signal<string>(this.read());
  readonly overview = resource({
    loader: async () => {
      const { data, error } = await this.api.client.GET('/api/v1/stats/overview');
      if (error) throw error;
      return data;
    },
  });
  readonly spaces = computed(() => (this.overview.hasValue() ? (this.overview.value().spaces ?? []) : []));
  readonly label = computed(() => this.selected() || 'all spaces');

  select(space: string): void {
    this.selected.set(space);
    try {
      localStorage.setItem(SPACE_KEY, space);
    } catch {
      /* ignore */
    }
  }

  /** Query parameter form: undefined when "all spaces". */
  param(): string | undefined {
    return this.selected() || undefined;
  }

  private read(): string {
    try {
      return localStorage.getItem(SPACE_KEY) ?? '';
    } catch {
      return '';
    }
  }
}
