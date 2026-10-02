import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'overview' },
  { path: 'overview', loadComponent: () => import('./pages/overview/overview').then((m) => m.OverviewPage), title: 'Overview · surrealmem' },
  { path: 'explorer', loadComponent: () => import('./pages/explorer/explorer').then((m) => m.ExplorerPage), title: 'Graph explorer · surrealmem' },
  { path: 'playground', loadComponent: () => import('./pages/playground/playground').then((m) => m.PlaygroundPage), title: 'Retrieval playground · surrealmem' },
  { path: 'conversations', loadComponent: () => import('./pages/conversations/conversations').then((m) => m.ConversationsPage), title: 'Conversations · surrealmem' },
  { path: 'analytics', loadComponent: () => import('./pages/analytics/analytics').then((m) => m.AnalyticsPage), title: 'Analytics · surrealmem' },
  { path: 'vectors', loadComponent: () => import('./pages/vectors/vectors').then((m) => m.VectorsPage), title: 'Vector space · surrealmem' },
  { path: 'curation', loadComponent: () => import('./pages/curation/curation').then((m) => m.CurationPage), title: 'Curation · surrealmem' },
  { path: 'operations', loadComponent: () => import('./pages/operations/operations').then((m) => m.OperationsPage), title: 'Operations · surrealmem' },
  { path: '**', redirectTo: 'overview' },
];
