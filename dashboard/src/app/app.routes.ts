import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'live', pathMatch: 'full' },
  {
    path: 'live',
    loadComponent: () =>
      import('./pages/live-view/live-view.component').then(m => m.LiveViewComponent),
  },
  {
    path: 'alerts',
    loadComponent: () =>
      import('./pages/alert-feed/alert-feed.component').then(m => m.AlertFeedComponent),
  },
  {
    path: 'events',
    loadComponent: () =>
      import('./pages/event-log/event-log.component').then(m => m.EventLogComponent),
  },
  {
    path: 'stats',
    loadComponent: () =>
      import('./pages/stats/stats.component').then(m => m.StatsComponent),
  },
  {
    path: 'config',
    loadComponent: () =>
      import('./pages/config/config.component').then(m => m.ConfigComponent),
  },
  {
    path: 'cameras',
    loadComponent: () =>
      import('./pages/cameras/cameras.component').then(m => m.CamerasComponent),
  },
  { path: '**', redirectTo: 'live' },
];
