import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { vi } from 'vitest';
import { App } from './app';

const overview = {
  tables: { entity: 2 },
  entities_by_type: { person: 2 },
  facts_by_status: {},
  jobs_by_status: {},
  relationship_kinds: [],
  spaces: ['work', 'personal'],
};

describe('App', () => {
  beforeEach(async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify(overview), { status: 200, headers: { 'content-type': 'application/json' } })),
    );
    vi.stubGlobal(
      'WebSocket',
      class {
        onopen: (() => void) | null = null;
        onclose: (() => void) | null = null;
        onerror: (() => void) | null = null;
        onmessage: ((m: MessageEvent<string>) => void) | null = null;
        close(): void {}
      },
    );
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter([])],
    }).compileComponents();
  });

  it('renders the shell with navigation and the spaces from the API', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    await new Promise((resolve) => setTimeout(resolve, 0));
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('aside')?.textContent).toContain('surrealmem');
    expect(compiled.querySelectorAll('nav a').length).toBe(8);
    expect(compiled.querySelectorAll('select option').length).toBe(3);
    expect(compiled.querySelector('[data-testid="token-banner"]')).toBeNull();
  });

  it('asks for the API token when the API answers 401', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ title: 'Unauthorized', status: 401 }), { status: 401, headers: { 'content-type': 'application/problem+json' } })),
    );
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    await new Promise((resolve) => setTimeout(resolve, 0));
    fixture.detectChanges();
    const banner = (fixture.nativeElement as HTMLElement).querySelector('[data-testid="token-banner"]');
    expect(banner?.textContent).toContain('SURREALMEM_API_TOKEN');
  });
});
