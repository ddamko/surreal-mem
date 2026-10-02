import { Injectable, effect, signal } from '@angular/core';

export type ThemeName = 'observatory' | 'observatory-light';
const KEY = 'surrealmem.theme';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly theme = signal<ThemeName>(this.read());

  constructor() {
    effect(() => {
      document.documentElement.setAttribute('data-theme', this.theme());
    });
  }

  toggle(): void {
    const next: ThemeName = this.theme() === 'observatory' ? 'observatory-light' : 'observatory';
    this.theme.set(next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* ignore */
    }
  }

  private read(): ThemeName {
    try {
      const stored = localStorage.getItem(KEY);
      if (stored === 'observatory' || stored === 'observatory-light') return stored;
    } catch {
      /* ignore */
    }
    return 'observatory';
  }
}
