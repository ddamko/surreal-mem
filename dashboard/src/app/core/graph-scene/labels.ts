/** Label placement for the canvas overlay: pure, so it can be unit-tested without WebGL. */

export interface LabelCandidate {
  id: string;
  /** Centre the box on (x, y) instead of placing it to the right of a node. */
  centered?: boolean;
  /** Screen-space centre and radius of the node, in CSS px. */
  x: number;
  y: number;
  r: number;
  text: string;
  /** Higher wins when labels compete for space. */
  priority: number;
  /** 0..1 opacity hint (depth fade in 3D). */
  alpha: number;
}

export interface PlacedLabel extends LabelCandidate {
  /** Top-left corner and box of the placed text, in CSS px. */
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface PlaceOptions {
  width: number;
  height: number;
  fontSize: number;
  maxLabels: number;
  /** Minimum node radius (px) for a label when the node is not prioritised. */
  minRadius: number;
  measure(text: string): number;
}

function overlaps(a: PlacedLabel, b: PlacedLabel): boolean {
  return a.left < b.left + b.width && a.left + a.width > b.left && a.top < b.top + b.height && a.top + a.height > b.top;
}

/** Greedy placement by priority: label to the right of the node, skip anything that collides or
 *  falls outside the viewport. Prioritised candidates (priority >= 1) ignore the radius threshold. */
export function placeLabels(candidates: LabelCandidate[], options: PlaceOptions, occupied: readonly PlacedLabel[] = []): PlacedLabel[] {
  const eligible = candidates.filter((c) => c.priority >= 1 || c.r >= options.minRadius);
  eligible.sort((a, b) => b.priority - a.priority || b.r - a.r);
  const placed: PlacedLabel[] = [];
  const height = options.fontSize * 1.3;
  for (const c of eligible) {
    if (placed.length >= options.maxLabels) break;
    const width = options.measure(c.text) + 6;
    const left = c.centered ? c.x - width / 2 : c.x + c.r + 4;
    const top = c.y - height / 2;
    if (left < 0 || left + width > options.width || top < 0 || top + height > options.height) continue;
    const box: PlacedLabel = { ...c, left, top, width, height };
    if (occupied.some((p) => overlaps(p, box)) || placed.some((p) => overlaps(p, box))) continue;
    placed.push(box);
  }
  return placed;
}
