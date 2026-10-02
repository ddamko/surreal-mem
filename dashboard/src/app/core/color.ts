/** Resolve CSS colors to `#rrggbb` for libraries that cannot parse modern CSS color syntax.
 *  daisyUI 5 themes and our ink variables are `oklch(...)`; Three.js, Sigma and ECharts want hex. */

const HEX = /^#([0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})$/i;

function clamp01(v: number): number {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

function toHex(r: number, g: number, b: number): string {
  const channel = (v: number): string => Math.round(clamp01(v) * 255).toString(16).padStart(2, '0');
  return `#${channel(r)}${channel(g)}${channel(b)}`;
}

function gamma(linear: number): number {
  return linear <= 0.0031308 ? 12.92 * linear : 1.055 * Math.pow(linear, 1 / 2.4) - 0.055;
}

function number(token: string, percentScale: number): number {
  const t = token.trim();
  if (t === 'none') return 0;
  if (t.endsWith('%')) return (parseFloat(t) / 100) * percentScale;
  return parseFloat(t);
}

/** OKLCH → sRGB (Björn Ottosson's matrices), gamut-clipped per channel. */
export function oklchToHex(l: number, c: number, h: number): string {
  const hr = (h * Math.PI) / 180;
  const a = c * Math.cos(hr);
  const b = c * Math.sin(hr);
  const l_ = l + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = l - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = l - 0.0894841775 * a - 1.291485548 * b;
  const L = l_ ** 3, M = m_ ** 3, S = s_ ** 3;
  const r = 4.0767416621 * L - 3.3077115913 * M + 0.2309699292 * S;
  const g = -1.2684380046 * L + 2.6097574011 * M - 0.3413193965 * S;
  const bl = -0.0041960863 * L - 0.7034186147 * M + 1.707614701 * S;
  return toHex(gamma(r), gamma(g), gamma(bl));
}

/** Any of `#hex`, `rgb()/rgba()`, `oklch()` → `#rrggbb`; anything else returns `fallback`. */
export function cssColor(value: string | null | undefined, fallback: string): string {
  const v = (value ?? '').trim();
  if (!v) return fallback;
  if (HEX.test(v)) {
    const hex = v.slice(1);
    if (hex.length === 6) return v.toLowerCase();
    if (hex.length === 8) return `#${hex.slice(0, 6)}`.toLowerCase();
    const [r, g, b] = hex.split('');
    return `#${r}${r}${g}${g}${b}${b}`.toLowerCase();
  }
  const fn = /^([a-z]+)\((.*)\)$/i.exec(v);
  if (!fn) return fallback;
  const name = fn[1].toLowerCase();
  const body = fn[2].split('/')[0];
  const parts = body.split(/[\s,]+/).filter(Boolean);
  if (parts.length < 3) return fallback;
  if (name === 'oklch') {
    return oklchToHex(number(parts[0], 1), number(parts[1], 0.4), number(parts[2].replace(/deg$/, ''), 360));
  }
  if (name === 'rgb' || name === 'rgba') {
    const [r, g, b] = parts.map((p) => number(p, 255) / 255);
    return toHex(r, g, b);
  }
  return fallback;
}

/** Read a CSS custom property from `:root` and resolve it to hex. */
export function themeColor(variable: string, fallback: string): string {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(variable);
  return cssColor(raw, fallback);
}
