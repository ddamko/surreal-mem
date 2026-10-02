/** Shared presentation helpers: entity-type colors, formatting. */
import { themeColor } from './color';

export const BASE_TYPES = ['person', 'organization', 'location', 'event', 'object', 'concept'] as const;
export type BaseType = (typeof BASE_TYPES)[number];

export function typeColor(baseType: string): string {
  return themeColor(`--type-${baseType}`, themeColor('--edge-ink', '#888888'));
}

export function shortId(id: string | null | undefined): string {
  if (!id) return '';
  const [, key] = id.split(':', 2);
  return key ? key.slice(-6) : id;
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function compact(n: number | null | undefined): string {
  if (n == null) return '–';
  return Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(n);
}
