import { describe, expect, it } from 'vitest';
import { cssColor, oklchToHex } from './color';

describe('cssColor', () => {
  it('passes hex through and expands short forms', () => {
    expect(cssColor('#3987E5', '#000')).toBe('#3987e5');
    expect(cssColor('#abc', '#000')).toBe('#aabbcc');
    expect(cssColor('#3987e580', '#000')).toBe('#3987e5');
  });

  it('converts rgb()', () => {
    expect(cssColor('rgb(255, 0, 0)', '#000')).toBe('#ff0000');
    expect(cssColor('rgb(0 128 255 / 50%)', '#000')).toBe('#0080ff');
  });

  it('converts oklch() including percent lightness and bare hue', () => {
    expect(oklchToHex(0, 0, 0)).toBe('#000000');
    expect(oklchToHex(1, 0, 0)).toBe('#ffffff');
    expect(cssColor('oklch(62.8% 0.2577 29.23)', '#000')).toBe('#ff0000');
    expect(cssColor('oklch(60% .02 262)', '#000')).toMatch(/^#[0-9a-f]{6}$/);
  });

  it('falls back on empty or unknown syntax', () => {
    expect(cssColor('', '#123456')).toBe('#123456');
    expect(cssColor('var(--edge-ink)', '#123456')).toBe('#123456');
    expect(cssColor('color-mix(in oklab, red, blue)', '#123456')).toBe('#123456');
  });
});
