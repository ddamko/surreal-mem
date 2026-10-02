import { Injectable, computed, signal } from '@angular/core';
import createClient from 'openapi-fetch';
import { environment } from '../../environments/environment';
import type { paths } from '../api/schema';

const TOKEN_KEY = 'surrealmem.token';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly tokenSignal = signal<string>(this.readToken());
  readonly token = this.tokenSignal.asReadonly();
  readonly hasToken = computed(() => this.tokenSignal().length > 0);
  /** True after the API answered 401 to the latest request; cleared by the next successful one. */
  readonly unauthorized = signal(false);
  private readonly baseUrl = environment.apiBase || location.origin;
  readonly client = createClient<paths>({ baseUrl: this.baseUrl });

  constructor() {
    this.client.use({
      onRequest: ({ request }) => {
        const token = this.tokenSignal();
        if (token) request.headers.set('Authorization', `Bearer ${token}`);
        return request;
      },
      onResponse: ({ response }) => {
        if (response.status === 401) this.unauthorized.set(true);
        else if (response.ok) this.unauthorized.set(false);
        return response;
      },
    });
  }

  /** Check a candidate token against the API without storing it. */
  async verifyToken(candidate: string): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/stats/overview`, {
        headers: { Authorization: `Bearer ${candidate}` },
      });
      return response.status !== 401;
    } catch {
      return false;
    }
  }

  setToken(token: string): void {
    this.tokenSignal.set(token);
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* storage unavailable */
    }
  }

  private readToken(): string {
    try {
      return localStorage.getItem(TOKEN_KEY) ?? environment.defaultToken;
    } catch {
      return environment.defaultToken;
    }
  }
}
