import { DestroyRef, Injectable, inject, signal } from '@angular/core';
import { ApiService } from './api';

export interface LiveEvent {
  table: string;
  action: 'CREATE' | 'UPDATE' | 'DELETE';
  id: string | null;
  record: Record<string, unknown>;
  at: string;
}

/** WebSocket relay of SurrealDB live queries (ADR-0017), with reconnect and a bounded feed. */
@Injectable({ providedIn: 'root' })
export class LiveService {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);
  private socket: WebSocket | null = null;
  private attempts = 0;
  private readonly listeners = new Set<(event: LiveEvent) => void>();

  readonly connected = signal(false);
  readonly feed = signal<LiveEvent[]>([]);
  readonly counter = signal(0);

  constructor() {
    this.connect();
    this.destroyRef.onDestroy(() => this.socket?.close());
  }

  on(listener: (event: LiveEvent) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private connect(): void {
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    const token = encodeURIComponent(this.api.token());
    const url = `${protocol}://${location.host}/api/v1/events?token=${token}`;
    try {
      this.socket = new WebSocket(url);
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.socket.onopen = () => {
      this.attempts = 0;
      this.connected.set(true);
    };
    this.socket.onclose = () => {
      this.connected.set(false);
      this.scheduleReconnect();
    };
    this.socket.onerror = () => this.socket?.close();
    this.socket.onmessage = (message: MessageEvent<string>) => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(message.data);
      } catch {
        return;
      }
      const event = parsed as Partial<LiveEvent> & { type?: string };
      if (event.type === 'ping' || !event.table) return;
      const live = event as LiveEvent;
      this.counter.update((n) => n + 1);
      this.feed.update((items) => [live, ...items].slice(0, 200));
      for (const listener of this.listeners) listener(live);
    };
  }

  private scheduleReconnect(): void {
    const delay = Math.min(30000, 1000 * 2 ** this.attempts++);
    setTimeout(() => this.connect(), delay);
  }
}
