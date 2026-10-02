import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { ApiService } from './core/api';
import { LiveService } from './core/live';
import { SpaceService } from './core/space';
import { ThemeService } from './core/theme';

interface NavItem {
  path: string;
  label: string;
  hint: string;
}

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  protected readonly api = inject(ApiService);
  protected readonly live = inject(LiveService);
  protected readonly space = inject(SpaceService);
  protected readonly theme = inject(ThemeService);
  protected tokenDraft = '';
  protected readonly nav: NavItem[] = [
    { path: '/overview', label: 'Overview', hint: 'What the memory holds and how it grows' },
    { path: '/explorer', label: 'Graph explorer', hint: 'Entities and their relationships' },
    { path: '/playground', label: 'Retrieval', hint: 'What an agent would be told' },
    { path: '/conversations', label: 'Conversations', hint: 'Source turns and what was extracted' },
    { path: '/analytics', label: 'Analytics', hint: 'Centrality, communities, kinds, health' },
    { path: '/vectors', label: 'Vector space', hint: 'Embeddings projected in 3D' },
    { path: '/curation', label: 'Curation', hint: 'Merges, kinds, archives' },
    { path: '/operations', label: 'Operations', hint: 'Jobs, workers, schema' },
  ];

  protected saveToken(): void {
    if (this.tokenDraft.trim()) {
      this.api.setToken(this.tokenDraft.trim());
      this.space.overview.reload();
      location.reload();
    }
  }
}
