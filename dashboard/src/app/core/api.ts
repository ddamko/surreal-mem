import { Injectable, signal } from '@angular/core';
import createClient from 'openapi-fetch';
import { environment } from '../../environments/environment';
import type { paths } from '../api/schema';

const TOKEN_KEY = 'surrealmem.token';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly tokenSignal = signal<string>(this.readToken());
  readonly token = this.tokenSignal.asReadonly();
  readonly client = createClient<paths>({ baseUrl: environment.apiBase || location.origin });

  constructor() {
    this.client.use({
      onRequest: ({ request }) => {
        const token = this.tokenSignal();
        if (token) request.headers.set('Authorization', `Bearer ${token}`);
        return request;
      },
    });
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
