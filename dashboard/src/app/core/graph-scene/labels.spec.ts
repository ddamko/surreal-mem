import { describe, expect, it } from 'vitest';
import { placeLabels, type LabelCandidate } from './labels';

const measure = (text: string): number => text.length * 6;
const options = { width: 400, height: 300, fontSize: 12, maxLabels: 50, minRadius: 5, measure };

function node(id: string, x: number, y: number, r: number, priority = 0): LabelCandidate {
  return { id, x, y, r, text: id, priority, alpha: 1 };
}

describe('placeLabels', () => {
  it('skips small nodes unless they are prioritised', () => {
    const placed = placeLabels([node('small', 50, 50, 2), node('focus', 150, 50, 2, 2), node('big', 250, 50, 8)], options);
    expect(placed.map((p) => p.id).sort()).toEqual(['big', 'focus']);
  });

  it('places by priority then radius and drops overlapping labels', () => {
    const placed = placeLabels([node('alpha', 100, 100, 6), node('beta', 104, 102, 10), node('gamma', 102, 101, 6, 1)], options);
    expect(placed[0].id).toBe('gamma');
    expect(placed).toHaveLength(1);
  });

  it('drops labels that leave the viewport', () => {
    const placed = placeLabels([node('edge', 395, 150, 6), node('top', 100, 2, 6), node('ok', 100, 150, 6)], options);
    expect(placed.map((p) => p.id)).toEqual(['ok']);
  });

  it('honours the label cap', () => {
    const many = Array.from({ length: 20 }, (_, i) => node(`n${i}`, 20, 10 + i * 14, 6));
    expect(placeLabels(many, { ...options, maxLabels: 5 })).toHaveLength(5);
  });
});
