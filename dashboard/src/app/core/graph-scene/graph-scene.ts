/** Our own graph renderer on Three.js (replaces Sigma, ADR-0034).
 *
 *  - Nodes: one `THREE.Points` with a disc shader; edges: one `LineSegments` with per-vertex color.
 *  - Layout: d3-force-3d, ticked from this scene's animation frame; nodes can be dragged in 2D.
 *  - Labels, focused edges, arrowheads and kind captions: a 2D canvas overlay, so text stays crisp.
 *  - 2D is an orthographic camera with pan/zoom; 3D is a perspective camera with OrbitControls.
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { cssColor } from '../color';
import { placeLabels, type LabelCandidate } from './labels';
import { LINE_FRAGMENT, LINE_VERTEX, NODE_FRAGMENT, NODE_VERTEX } from './shaders';
import { GraphSimulation } from './simulation';
import type { GraphInput, SceneEvents, SceneFocus, SceneLink, SceneMode, SceneNode, SceneTheme } from './types';

const BASE_NODE_ALPHA = 0.96;
const DIM_NODE_ALPHA = 0.1;
const BASE_EDGE_ALPHA = 0.22;
const DIM_EDGE_ALPHA = 0.04;
const FOCUS_EDGE_ALPHA = 0.85;
const CLICK_SLOP_PX = 4;
const MIN_ZOOM = 0.02;
const MAX_ZOOM = 40;

interface Tween {
  start: number;
  duration: number;
  from: number[];
  to: number[];
  apply(values: number[]): void;
}

interface PointerState {
  sx: number;
  sy: number;
  camX: number;
  camY: number;
  node: SceneNode | null;
  moved: boolean;
}

function ease(t: number): number {
  return t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
}

export class GraphScene {
  private readonly renderer: THREE.WebGLRenderer;
  private readonly overlay: HTMLCanvasElement;
  private readonly ctx: CanvasRenderingContext2D;
  private readonly scene = new THREE.Scene();
  private readonly ortho = new THREE.OrthographicCamera(-1, 1, 1, -1, -5000, 5000);
  private readonly persp = new THREE.PerspectiveCamera(50, 1, 1, 20000);
  private orbit: OrbitControls | null = null;
  private mode: SceneMode = '2d';

  private readonly sim = new GraphSimulation();
  private nodes: SceneNode[] = [];
  private links: SceneLink[] = [];
  private readonly byId = new Map<string, SceneNode>();
  private readonly index = new Map<string, number>();
  private readonly linksOf = new Map<string, SceneLink[]>();

  private readonly nodeMaterial: THREE.ShaderMaterial;
  private readonly lineMaterial: THREE.ShaderMaterial;
  private nodeGeometry = new THREE.BufferGeometry();
  private lineGeometry = new THREE.BufferGeometry();
  private readonly haloGeometry = new THREE.BufferGeometry();
  private readonly points: THREE.Points;
  private readonly lines: THREE.LineSegments;
  private readonly halos: THREE.Points;
  private nodePositions = new Float32Array(0);
  private nodeAlphas = new Float32Array(0);
  private linePositions = new Float32Array(0);
  private lineColors = new Float32Array(0);
  private lineAlphas = new Float32Array(0);
  /** Per node: screen x, screen y, screen radius, view depth. */
  private screen = new Float32Array(0);

  private focus: SceneFocus = { hovered: null, selected: null, pathEdges: new Set() };
  private focusNodes = new Set<string>();
  private theme: SceneTheme;
  private readonly events: SceneEvents;
  private readonly textWidths = new Map<string, number>();

  private frame = 0;
  private width = 0;
  private height = 0;
  private dirty = true;
  private userMoved = false;
  /** Auto-fit while the user has not moved the camera: once at the deadline, once more when the layout settles. */
  private autoFit: { deadline: number; onSettle: boolean } | null = null;
  private pointer: PointerState | null = null;
  private hoveredId: string | null = null;
  private tween: Tween | null = null;
  private readonly timer = new THREE.Timer();
  private readonly observer: ResizeObserver;
  /** Set by the ResizeObserver; the actual work happens in the next frame so the observer callback
   *  never changes layout itself (that is what "ResizeObserver loop completed" complains about). */
  private needsResize = true;
  private readonly tmp = new THREE.Vector3();
  private readonly listeners: [string, EventListener, AddEventListenerOptions?][] = [];

  constructor(
    private readonly container: HTMLElement,
    theme: SceneTheme,
    events: SceneEvents = {},
  ) {
    this.theme = theme;
    this.events = events;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.setClearColor(0x000000, 0);
    Object.assign(this.renderer.domElement.style, { position: 'absolute', inset: '0', width: '100%', height: '100%', display: 'block', touchAction: 'none' });
    container.appendChild(this.renderer.domElement);
    this.overlay = document.createElement('canvas');
    Object.assign(this.overlay.style, { position: 'absolute', inset: '0', width: '100%', height: '100%', pointerEvents: 'none' });
    container.appendChild(this.overlay);
    this.ctx = this.overlay.getContext('2d') as CanvasRenderingContext2D;

    this.nodeMaterial = new THREE.ShaderMaterial({
      vertexShader: NODE_VERTEX,
      fragmentShader: NODE_FRAGMENT,
      uniforms: { uScale: { value: 1 }, uPerspective: { value: 0 } },
      transparent: true,
      depthWrite: false,
      depthTest: false,
    });
    this.lineMaterial = new THREE.ShaderMaterial({
      vertexShader: LINE_VERTEX,
      fragmentShader: LINE_FRAGMENT,
      transparent: true,
      depthWrite: false,
      depthTest: false,
    });
    this.lines = new THREE.LineSegments(this.lineGeometry, this.lineMaterial);
    this.points = new THREE.Points(this.nodeGeometry, this.nodeMaterial);
    this.halos = new THREE.Points(this.haloGeometry, this.nodeMaterial);
    this.lines.renderOrder = 0;
    this.halos.renderOrder = 1;
    this.points.renderOrder = 2;
    this.lines.frustumCulled = false;
    this.points.frustumCulled = false;
    this.halos.frustumCulled = false;
    this.scene.add(this.lines, this.halos, this.points);
    this.haloGeometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(6), 3));
    this.haloGeometry.setAttribute('color', new THREE.BufferAttribute(new Float32Array(6), 3));
    this.haloGeometry.setAttribute('size', new THREE.BufferAttribute(new Float32Array(2), 1));
    this.haloGeometry.setAttribute('alpha', new THREE.BufferAttribute(new Float32Array(2), 1));
    this.haloGeometry.setAttribute('ring', new THREE.BufferAttribute(new Float32Array([1, 1]), 1));
    this.haloGeometry.setDrawRange(0, 0);

    this.ortho.position.set(0, 0, 1000);
    this.persp.position.set(0, 0, 600);
    container.dataset['graphMode'] = this.mode;

    const el = this.renderer.domElement;
    this.listen(el, 'pointerdown', (e) => this.onPointerDown(e as PointerEvent));
    this.listen(el, 'pointermove', (e) => this.onPointerMove(e as PointerEvent));
    this.listen(el, 'pointerup', (e) => this.onPointerUp(e as PointerEvent));
    this.listen(el, 'pointercancel', (e) => this.onPointerUp(e as PointerEvent));
    this.listen(el, 'pointerleave', () => this.setHovered(null));
    this.listen(el, 'wheel', (e) => this.onWheel(e as WheelEvent), { passive: false });
    this.listen(el, 'dblclick', () => this.fit());
    this.observer = new ResizeObserver(() => (this.needsResize = true));
    this.observer.observe(container);
    this.resize();
    this.frame = requestAnimationFrame((t) => this.tick(t));
  }

  // ------------------------------------------------------------------ public API

  /** Replace the graph. Positions of nodes that already exist are kept; new nodes spawn next to a
   *  neighbour so expansion grows out of the selection instead of flashing in from the edges. */
  setGraph(input: GraphInput): void {
    const previous = this.byId;
    const next = new Map<string, SceneNode>();
    let topologyChanged = input.nodes.length !== previous.size || input.edges.length !== this.links.length;
    const spread = Math.max(80, Math.sqrt(input.nodes.length) * 28);
    for (const n of input.nodes) {
      const color = new THREE.Color(cssColor(n.color, '#8a93a8'));
      const old = previous.get(n.id);
      if (!old) topologyChanged = true;
      next.set(n.id, {
        id: n.id,
        label: n.label,
        size: n.size,
        rgb: [color.r, color.g, color.b],
        x: old?.x ?? Number.NaN,
        y: old?.y ?? Number.NaN,
        z: old?.z ?? 0,
        vx: old?.vx ?? 0,
        vy: old?.vy ?? 0,
        vz: old?.vz ?? 0,
      });
    }
    const links: SceneLink[] = [];
    const linksOf = new Map<string, SceneLink[]>();
    const oldLinkIds = new Set(this.links.map((l) => l.id));
    for (const e of input.edges) {
      const source = next.get(e.source);
      const target = next.get(e.target);
      if (!source || !target || source === target) continue;
      const link: SceneLink = { id: e.id, source, target, kind: e.kind };
      links.push(link);
      (linksOf.get(source.id) ?? linksOf.set(source.id, []).get(source.id)!).push(link);
      (linksOf.get(target.id) ?? linksOf.set(target.id, []).get(target.id)!).push(link);
      if (!oldLinkIds.has(e.id)) topologyChanged = true;
    }
    // Spawn positions: beside a placed neighbour when there is one, otherwise a random spot.
    for (const node of next.values()) {
      if (!Number.isNaN(node.x)) continue;
      const anchor = linksOf.get(node.id)?.map((l) => (l.source === node ? l.target : l.source)).find((n) => !Number.isNaN(n.x));
      const jitter = (): number => (Math.random() - 0.5) * 24;
      node.x = anchor ? anchor.x + jitter() : (Math.random() - 0.5) * spread;
      node.y = anchor ? anchor.y + jitter() : (Math.random() - 0.5) * spread;
      node.z = this.mode === '3d' ? (anchor ? anchor.z + jitter() : (Math.random() - 0.5) * spread * 0.5) : 0;
    }

    const fresh = previous.size === 0;
    this.byId.clear();
    for (const [id, n] of next) this.byId.set(id, n);
    this.nodes = [...next.values()];
    this.links = links;
    this.linksOf.clear();
    for (const [id, l] of linksOf) this.linksOf.set(id, l);
    this.index.clear();
    this.nodes.forEach((n, i) => this.index.set(n.id, i));

    this.allocate();
    this.sim.setData(this.nodes, this.links, topologyChanged ? (fresh ? 1 : 0.5) : 0);
    if (fresh || topologyChanged) {
      this.sim.warmUp(fresh ? 160 : 40);
      if (fresh || !this.userMoved) this.autoFit = { deadline: performance.now() + 900, onSettle: true };
    }
    this.applyFocus();
    this.dirty = true;
  }

  setFocus(focus: SceneFocus): void {
    this.focus = focus;
    this.applyFocus();
    this.dirty = true;
  }

  setTheme(theme: SceneTheme): void {
    this.theme = theme;
    this.textWidths.clear();
    this.dirty = true;
  }

  setMode(mode: SceneMode): void {
    if (mode === this.mode) return;
    this.mode = mode;
    this.container.dataset['graphMode'] = mode;
    this.sim.setDimensions(mode === '3d' ? 3 : 2);
    if (mode === '3d') {
      this.orbit = new OrbitControls(this.persp, this.renderer.domElement);
      this.orbit.enableDamping = true;
      this.orbit.dampingFactor = 0.08;
      this.orbit.addEventListener('start', () => {
        this.userMoved = true;
        this.tween = null;
      });
      this.persp.position.set(this.ortho.position.x, this.ortho.position.y, 600);
      this.orbit.target.set(this.ortho.position.x, this.ortho.position.y, 0);
    } else {
      this.orbit?.dispose();
      this.orbit = null;
      this.ortho.position.set(this.persp.position.x, this.persp.position.y, 1000);
    }
    this.nodeMaterial.uniforms['uPerspective'].value = mode === '3d' ? 1 : 0;
    this.nodeMaterial.depthTest = mode === '3d';
    this.lineMaterial.depthTest = mode === '3d';
    this.userMoved = false;
    this.autoFit = { deadline: performance.now() + 700, onSettle: true };
    this.dirty = true;
  }

  getMode(): SceneMode {
    return this.mode;
  }

  /** Shake the layout loose again. */
  relayout(): void {
    this.sim.reheat(0.8);
    this.userMoved = false;
    this.autoFit = { deadline: performance.now() + 1200, onSettle: true };
  }

  /** Frame the graph. With many nodes the bounds are the 3rd–97th percentiles, so a few far-flung
   *  isolates do not shrink the main structure to a dot; they remain reachable by panning. */
  fit(animate = true): void {
    if (!this.nodes.length || !this.width || !this.height) return;
    const [minX, maxX] = this.bounds((n) => n.x);
    const [minY, maxY] = this.bounds((n) => n.y);
    const [minZ, maxZ] = this.bounds((n) => n.z);
    const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2, cz = (minZ + maxZ) / 2;
    if (this.mode === '2d') {
      const zoom = this.nodes.length < 2 ? 4 : Math.min(MAX_ZOOM / 4, Math.max(MIN_ZOOM, Math.min((this.width - 96) / Math.max(1, maxX - minX), (this.height - 96) / Math.max(1, maxY - minY))));
      this.animateCamera(cx, cy, zoom, animate ? 600 : 0);
    } else if (this.orbit) {
      const halfW = Math.max(20, (maxX - minX) / 2), halfH = Math.max(20, (maxY - minY) / 2), halfD = Math.max(20, (maxZ - minZ) / 2);
      const tanV = Math.tan(THREE.MathUtils.degToRad(this.persp.fov / 2));
      const tanH = tanV * this.persp.aspect;
      const distance = Math.max(halfH / tanV, halfW / tanH) * 1.15 + halfD;
      const dir = this.persp.position.clone().sub(this.orbit.target).normalize();
      if (!dir.lengthSq()) dir.set(0, 0, 1);
      const target = new THREE.Vector3(cx, cy, cz);
      this.animateOrbit(target, dir.multiplyScalar(distance).add(target), animate ? 600 : 0);
    }
    this.dirty = true;
  }

  private bounds(pick: (n: SceneNode) => number): [number, number] {
    const values = this.nodes.map((n) => pick(n)).sort((a, b) => a - b);
    const pad = 6;
    if (values.length < 50) return [values[0] - pad, values[values.length - 1] + pad];
    const lo = values[Math.floor(values.length * 0.03)];
    const hi = values[Math.ceil(values.length * 0.97) - 1];
    return [lo - pad, hi + pad];
  }

  /** Bring one node to the centre, zooming in a little if the view is wide. */
  focusNode(id: string): void {
    const node = this.byId.get(id);
    if (!node) return;
    this.userMoved = true;
    if (this.mode === '2d') {
      this.animateCamera(node.x, node.y, Math.max(this.ortho.zoom, 2.5), 500);
    } else if (this.orbit) {
      const dir = this.persp.position.clone().sub(this.orbit.target).normalize();
      const target = new THREE.Vector3(node.x, node.y, node.z);
      this.animateOrbit(target, dir.multiplyScalar(160).add(target), 500);
    }
  }

  dispose(): void {
    cancelAnimationFrame(this.frame);
    this.observer.disconnect();
    for (const [type, fn, options] of this.listeners) this.renderer.domElement.removeEventListener(type, fn, options);
    this.orbit?.dispose();
    this.nodeGeometry.dispose();
    this.lineGeometry.dispose();
    this.haloGeometry.dispose();
    this.nodeMaterial.dispose();
    this.lineMaterial.dispose();
    this.renderer.dispose();
    this.renderer.domElement.remove();
    this.overlay.remove();
  }

  // ------------------------------------------------------------------ buffers and styling

  private allocate(): void {
    const n = this.nodes.length;
    const m = this.links.length;
    this.nodePositions = new Float32Array(n * 3);
    this.nodeAlphas = new Float32Array(n).fill(BASE_NODE_ALPHA);
    const colors = new Float32Array(n * 3);
    const sizes = new Float32Array(n);
    this.nodes.forEach((node, i) => {
      colors.set(node.rgb, i * 3);
      sizes[i] = node.size;
    });
    this.nodeGeometry.dispose();
    this.nodeGeometry = new THREE.BufferGeometry();
    this.nodeGeometry.setAttribute('position', new THREE.BufferAttribute(this.nodePositions, 3));
    this.nodeGeometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    this.nodeGeometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));
    this.nodeGeometry.setAttribute('alpha', new THREE.BufferAttribute(this.nodeAlphas, 1));
    this.nodeGeometry.setAttribute('ring', new THREE.BufferAttribute(new Float32Array(n), 1));
    this.points.geometry = this.nodeGeometry;

    this.linePositions = new Float32Array(m * 6);
    this.lineColors = new Float32Array(m * 6);
    this.lineAlphas = new Float32Array(m * 2).fill(BASE_EDGE_ALPHA);
    this.links.forEach((l, i) => {
      this.lineColors.set(l.source.rgb, i * 6);
      this.lineColors.set(l.target.rgb, i * 6 + 3);
    });
    this.lineGeometry.dispose();
    this.lineGeometry = new THREE.BufferGeometry();
    this.lineGeometry.setAttribute('position', new THREE.BufferAttribute(this.linePositions, 3));
    this.lineGeometry.setAttribute('color', new THREE.BufferAttribute(this.lineColors, 3));
    this.lineGeometry.setAttribute('alpha', new THREE.BufferAttribute(this.lineAlphas, 1));
    this.lines.geometry = this.lineGeometry;
    this.screen = new Float32Array(n * 4);
    this.writePositions();
  }

  private writePositions(): void {
    if (!this.nodeGeometry.attributes['position'] || !this.lineGeometry.attributes['position']) return;
    for (let i = 0; i < this.nodes.length; i++) {
      const n = this.nodes[i];
      this.nodePositions[i * 3] = n.x;
      this.nodePositions[i * 3 + 1] = n.y;
      this.nodePositions[i * 3 + 2] = n.z;
    }
    for (let i = 0; i < this.links.length; i++) {
      const { source: s, target: t } = this.links[i];
      this.linePositions.set([s.x, s.y, s.z, t.x, t.y, t.z], i * 6);
    }
    this.nodeGeometry.attributes['position'].needsUpdate = true;
    this.lineGeometry.attributes['position'].needsUpdate = true;
  }

  /** Alpha per node and edge from hover/selection/path state. */
  private applyFocus(): void {
    const focusId = this.focus.hovered ?? this.focus.selected;
    this.focusNodes = new Set<string>();
    if (focusId && this.byId.has(focusId)) {
      this.focusNodes.add(focusId);
      for (const l of this.linksOf.get(focusId) ?? []) this.focusNodes.add(l.source.id === focusId ? l.target.id : l.source.id);
    }
    for (const id of this.pathNodeIds()) this.focusNodes.add(id);
    const dimming = this.focusNodes.size > 0;
    for (let i = 0; i < this.nodes.length; i++) {
      this.nodeAlphas[i] = !dimming || this.focusNodes.has(this.nodes[i].id) ? BASE_NODE_ALPHA : DIM_NODE_ALPHA;
    }
    const text = new THREE.Color(cssColor(this.theme.text, '#dddddd'));
    const primary = new THREE.Color(cssColor(this.theme.primary, '#e8b04b'));
    for (let i = 0; i < this.links.length; i++) {
      const l = this.links[i];
      let alpha = dimming ? DIM_EDGE_ALPHA : BASE_EDGE_ALPHA;
      let sc = l.source.rgb, tc = l.target.rgb;
      if (this.focus.pathEdges.has(l.id)) {
        alpha = 1;
        sc = tc = [primary.r, primary.g, primary.b];
      } else if (focusId && (l.source.id === focusId || l.target.id === focusId)) {
        alpha = FOCUS_EDGE_ALPHA;
        sc = tc = [text.r, text.g, text.b];
      }
      this.lineAlphas[i * 2] = alpha;
      this.lineAlphas[i * 2 + 1] = alpha;
      this.lineColors.set(sc, i * 6);
      this.lineColors.set(tc, i * 6 + 3);
    }
    if (this.nodeGeometry.attributes['alpha']) this.nodeGeometry.attributes['alpha'].needsUpdate = true;
    if (this.lineGeometry.attributes['alpha']) {
      this.lineGeometry.attributes['alpha'].needsUpdate = true;
      this.lineGeometry.attributes['color'].needsUpdate = true;
    }
  }

  private pathNodeIds(): string[] {
    if (!this.focus.pathEdges.size) return [];
    const ids: string[] = [];
    for (const l of this.links) if (this.focus.pathEdges.has(l.id)) ids.push(l.source.id, l.target.id);
    return ids;
  }

  private updateHalos(): void {
    const slots: [SceneNode | undefined, THREE.Color, number][] = [
      [this.focus.selected ? this.byId.get(this.focus.selected) : undefined, new THREE.Color(cssColor(this.theme.primary, '#e8b04b')), 0.9],
      [this.focus.hovered && this.focus.hovered !== this.focus.selected ? this.byId.get(this.focus.hovered) : undefined, new THREE.Color(cssColor(this.theme.text, '#dddddd')), 0.6],
    ];
    const pos = this.haloGeometry.attributes['position'] as THREE.BufferAttribute;
    const col = this.haloGeometry.attributes['color'] as THREE.BufferAttribute;
    const size = this.haloGeometry.attributes['size'] as THREE.BufferAttribute;
    const alpha = this.haloGeometry.attributes['alpha'] as THREE.BufferAttribute;
    const pulse = 1 + 0.08 * Math.sin(this.timer.getElapsed() * 3);
    let count = 0;
    slots.forEach(([node, color, a], slot) => {
      if (!node) return;
      pos.setXYZ(count, node.x, node.y, node.z);
      col.setXYZ(count, color.r, color.g, color.b);
      size.setX(count, node.size * (slot === 0 ? 1.75 * pulse : 1.5));
      alpha.setX(count, a);
      count++;
    });
    this.haloGeometry.setDrawRange(0, count);
    pos.needsUpdate = col.needsUpdate = size.needsUpdate = alpha.needsUpdate = true;
  }

  // ------------------------------------------------------------------ frame loop

  private tick(now: number): void {
    this.frame = requestAnimationFrame((t) => this.tick(t));
    if (this.needsResize) this.resize();
    if (!this.width || !this.height) return;
    this.timer.update(now);
    const moved = this.nodes.length > 0 && this.sim.step();
    if (moved) this.writePositions();
    if (this.tween) this.runTween(now);
    if (this.orbit) this.orbit.update();
    if (this.autoFit && !this.userMoved) {
      const settled = !this.sim.active();
      if (now >= this.autoFit.deadline || settled) {
        this.fit();
        this.autoFit = settled || !this.autoFit.onSettle ? null : { deadline: Infinity, onSettle: true };
      }
    } else if (this.autoFit && this.userMoved) {
      this.autoFit = null;
    }
    const camera = this.camera();
    camera.updateMatrixWorld();
    const dpr = this.renderer.getPixelRatio();
    this.nodeMaterial.uniforms['uScale'].value = this.mode === '2d' ? this.ortho.zoom * dpr : ((this.height * dpr) / 2) / Math.tan(THREE.MathUtils.degToRad(this.persp.fov / 2));
    this.updateHalos();
    this.renderer.render(this.scene, camera);
    this.project(camera);
    this.drawOverlay();
    this.dirty = false;
  }

  private camera(): THREE.Camera {
    return this.mode === '2d' ? this.ortho : this.persp;
  }

  private project(camera: THREE.Camera): void {
    const halfH = this.height / 2;
    const k = this.mode === '2d' ? this.ortho.zoom : halfH / Math.tan(THREE.MathUtils.degToRad(this.persp.fov / 2));
    for (let i = 0; i < this.nodes.length; i++) {
      const n = this.nodes[i];
      this.tmp.set(n.x, n.y, n.z).applyMatrix4(camera.matrixWorldInverse);
      const depth = -this.tmp.z;
      this.tmp.applyMatrix4(camera.projectionMatrix);
      const o = i * 4;
      this.screen[o] = ((this.tmp.x + 1) / 2) * this.width;
      this.screen[o + 1] = ((1 - this.tmp.y) / 2) * this.height;
      this.screen[o + 2] = this.mode === '2d' ? n.size * k : depth > 1 ? (n.size * k) / depth : 0;
      this.screen[o + 3] = depth;
    }
  }

  private drawOverlay(): void {
    const ctx = this.ctx;
    const dpr = Math.min(devicePixelRatio, 2);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, this.width, this.height);
    if (!this.nodes.length) return;
    const text = cssColor(this.theme.text, '#dddddd');
    const halo = cssColor(this.theme.background, '#101420');
    const primary = cssColor(this.theme.primary, '#e8b04b');
    const ink = cssColor(this.theme.ink, '#8a93a8');
    const focusId = this.focus.hovered ?? this.focus.selected;

    // Focused edges first so labels sit on top.
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    const captions: LabelCandidate[] = [];
    const drawEdge = (l: SceneLink, color: string, width: number, priority: number): void => {
      const si = this.index.get(l.source.id)!, ti = this.index.get(l.target.id)!;
      const sx = this.screen[si * 4], sy = this.screen[si * 4 + 1], sr = this.screen[si * 4 + 2];
      const tx = this.screen[ti * 4], ty = this.screen[ti * 4 + 1], tr = this.screen[ti * 4 + 2];
      if (this.screen[si * 4 + 3] <= 0 || this.screen[ti * 4 + 3] <= 0) return;
      const dx = tx - sx, dy = ty - sy;
      const len = Math.hypot(dx, dy);
      if (len < sr + tr + 6) return;
      const ux = dx / len, uy = dy / len;
      const ax = sx + ux * sr, ay = sy + uy * sr;
      const bx = tx - ux * (tr + 2), by = ty - uy * (tr + 2);
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = width;
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      ctx.lineTo(bx, by);
      ctx.stroke();
      const head = 5 + width * 1.5;
      ctx.beginPath();
      ctx.moveTo(bx, by);
      ctx.lineTo(bx - ux * head - uy * head * 0.55, by - uy * head + ux * head * 0.55);
      ctx.lineTo(bx - ux * head + uy * head * 0.55, by - uy * head - ux * head * 0.55);
      ctx.closePath();
      ctx.fill();
      if (len > 90) {
        captions.push({ id: `caption:${l.id}`, x: (ax + bx) / 2, y: (ay + by) / 2 - 7, r: 0, text: l.kind.toLowerCase().replace(/_/g, ' '), priority, alpha: 1, centered: true });
      }
    };
    if (focusId) for (const l of this.linksOf.get(focusId) ?? []) if (!this.focus.pathEdges.has(l.id)) drawEdge(l, text, 1.5, 1);
    if (this.focus.pathEdges.size) for (const l of this.links) if (this.focus.pathEdges.has(l.id)) drawEdge(l, primary, 2.5, 2);

    // Labels: focused nodes always, then the biggest on screen that still have room.
    const fontSize = 12;
    const font = `500 ${fontSize}px ${this.theme.font}`;
    ctx.font = font;
    const measure = (t: string): number => {
      const key = `${ctx.font}|${t}`;
      let w = this.textWidths.get(key);
      if (w === undefined) {
        w = ctx.measureText(t).width;
        this.textWidths.set(key, w);
      }
      return w;
    };
    const candidates: LabelCandidate[] = [];
    const nearest = this.mode === '3d' ? this.depthRange() : null;
    for (let i = 0; i < this.nodes.length; i++) {
      const o = i * 4;
      const depth = this.screen[o + 3];
      if (depth <= 0) continue;
      const id = this.nodes[i].id;
      const focused = this.focusNodes.has(id);
      const alphaHint = this.nodeAlphas[i] < 0.5 ? 0 : nearest ? 1 - 0.6 * ((depth - nearest[0]) / Math.max(1, nearest[1] - nearest[0])) : 1;
      if (alphaHint <= 0) continue;
      candidates.push({
        id,
        x: this.screen[o],
        y: this.screen[o + 1],
        r: this.screen[o + 2],
        text: this.nodes[i].label,
        priority: id === focusId || id === this.focus.selected ? 3 : focused ? 2 : 0,
        alpha: alphaHint,
      });
    }
    const placed = placeLabels(candidates, { width: this.width, height: this.height, fontSize, maxLabels: 220, minRadius: 5.5, measure });
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    for (const p of placed) {
      const strong = p.priority >= 2;
      ctx.font = strong ? `600 ${fontSize + 1}px ${this.theme.font}` : font;
      ctx.globalAlpha = Math.max(0.35, p.alpha);
      ctx.lineWidth = 3.5;
      ctx.strokeStyle = halo;
      ctx.strokeText(p.text, p.left + 3, p.y);
      ctx.fillStyle = text;
      ctx.fillText(p.text, p.left + 3, p.y);
    }
    ctx.globalAlpha = 1;

    // Kind captions on focused edges, only where they do not collide with anything placed above.
    if (captions.length) {
      ctx.font = `500 10px ${this.theme.mono}`;
      const placedCaptions = placeLabels(captions, { width: this.width, height: this.height, fontSize: 10, maxLabels: 40, minRadius: 0, measure }, placed);
      ctx.textAlign = 'center';
      for (const c of placedCaptions) {
        ctx.lineWidth = 3;
        ctx.strokeStyle = halo;
        ctx.strokeText(c.text, c.x, c.y);
        ctx.fillStyle = c.priority >= 2 ? primary : ink;
        ctx.fillText(c.text, c.x, c.y);
      }
    }
  }

  private depthRange(): [number, number] {
    let min = Infinity, max = -Infinity;
    for (let i = 0; i < this.nodes.length; i++) {
      const d = this.screen[i * 4 + 3];
      if (d <= 0) continue;
      min = Math.min(min, d);
      max = Math.max(max, d);
    }
    return [min, max];
  }

  // ------------------------------------------------------------------ camera helpers

  private resize(): void {
    this.needsResize = false;
    const rect = this.container.getBoundingClientRect();
    const w = rect.width, h = rect.height;
    if (!w || !h) {
      this.width = this.height = 0;
      return;
    }
    if (w === this.width && h === this.height) return;
    this.width = w;
    this.height = h;
    // Drawing buffers only (updateStyle = false): the canvases are sized by CSS, so rounding can
    // never make them a pixel larger than the container and trigger a scrollbar.
    this.renderer.setSize(w, h, false);
    const dpr = Math.min(devicePixelRatio, 2);
    this.overlay.width = Math.round(w * dpr);
    this.overlay.height = Math.round(h * dpr);
    this.ortho.left = -w / 2;
    this.ortho.right = w / 2;
    this.ortho.top = h / 2;
    this.ortho.bottom = -h / 2;
    this.ortho.updateProjectionMatrix();
    this.persp.aspect = w / h;
    this.persp.updateProjectionMatrix();
    this.dirty = true;
  }

  private animateCamera(x: number, y: number, zoom: number, duration: number): void {
    const from = [this.ortho.position.x, this.ortho.position.y, Math.log(this.ortho.zoom)];
    const to = [x, y, Math.log(zoom)];
    const apply = (v: number[]): void => {
      this.ortho.position.x = v[0];
      this.ortho.position.y = v[1];
      this.ortho.zoom = Math.exp(v[2]);
      this.ortho.updateProjectionMatrix();
    };
    if (duration <= 0) {
      apply(to);
      this.tween = null;
      return;
    }
    this.tween = { start: performance.now(), duration, from, to, apply };
  }

  private animateOrbit(target: THREE.Vector3, position: THREE.Vector3, duration: number): void {
    const orbit = this.orbit;
    if (!orbit) return;
    const from = [orbit.target.x, orbit.target.y, orbit.target.z, this.persp.position.x, this.persp.position.y, this.persp.position.z];
    const to = [target.x, target.y, target.z, position.x, position.y, position.z];
    const apply = (v: number[]): void => {
      orbit.target.set(v[0], v[1], v[2]);
      this.persp.position.set(v[3], v[4], v[5]);
    };
    if (duration <= 0) {
      apply(to);
      this.tween = null;
      return;
    }
    this.tween = { start: performance.now(), duration, from, to, apply };
  }

  private runTween(now: number): void {
    const t = this.tween!;
    const k = ease(Math.min(1, (now - t.start) / t.duration));
    t.apply(t.from.map((f, i) => f + (t.to[i] - f) * k));
    if (k >= 1) this.tween = null;
  }

  private worldX(sx: number): number {
    return this.ortho.position.x + (sx - this.width / 2) / this.ortho.zoom;
  }

  private worldY(sy: number): number {
    return this.ortho.position.y - (sy - this.height / 2) / this.ortho.zoom;
  }

  // ------------------------------------------------------------------ interaction

  private listen(el: HTMLElement, type: string, fn: EventListener, options?: AddEventListenerOptions): void {
    el.addEventListener(type, fn, options);
    this.listeners.push([type, fn, options]);
  }

  private local(e: PointerEvent | WheelEvent): [number, number] {
    const r = this.renderer.domElement.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  }

  private pick(sx: number, sy: number): SceneNode | null {
    let best: SceneNode | null = null;
    let bestDist = Infinity;
    for (let i = 0; i < this.nodes.length; i++) {
      const o = i * 4;
      if (this.screen[o + 3] <= 0) continue;
      const reach = Math.max(6, this.screen[o + 2]) + 2;
      const dx = this.screen[o] - sx, dy = this.screen[o + 1] - sy;
      const d = dx * dx + dy * dy;
      if (d <= reach * reach && d < bestDist) {
        bestDist = d;
        best = this.nodes[i];
      }
    }
    return best;
  }

  private setHovered(id: string | null): void {
    if (id === this.hoveredId) return;
    this.hoveredId = id;
    this.renderer.domElement.style.cursor = id ? 'pointer' : this.pointer ? 'grabbing' : 'default';
    this.events.nodeHover?.(id);
  }

  private onPointerDown(e: PointerEvent): void {
    if (e.button !== 0) return;
    const [sx, sy] = this.local(e);
    const node = this.pick(sx, sy);
    this.pointer = { sx, sy, camX: this.ortho.position.x, camY: this.ortho.position.y, node, moved: false };
    this.renderer.domElement.setPointerCapture(e.pointerId);
    if (node && this.mode === '2d') {
      this.sim.dragStart(node);
      this.tween = null;
    }
    if (this.mode === '2d') this.renderer.domElement.style.cursor = node ? 'grabbing' : 'grabbing';
  }

  private onPointerMove(e: PointerEvent): void {
    const [sx, sy] = this.local(e);
    const p = this.pointer;
    if (!p) {
      this.setHovered(this.pick(sx, sy)?.id ?? null);
      return;
    }
    const dx = sx - p.sx, dy = sy - p.sy;
    if (!p.moved && Math.hypot(dx, dy) > CLICK_SLOP_PX) p.moved = true;
    if (!p.moved || this.mode !== '2d') return;
    if (p.node) {
      this.sim.drag(p.node, this.worldX(sx), this.worldY(sy));
    } else {
      this.ortho.position.x = p.camX - dx / this.ortho.zoom;
      this.ortho.position.y = p.camY + dy / this.ortho.zoom;
      this.userMoved = true;
      this.tween = null;
    }
  }

  private onPointerUp(e: PointerEvent): void {
    const p = this.pointer;
    if (!p) return;
    this.pointer = null;
    if (this.renderer.domElement.hasPointerCapture(e.pointerId)) this.renderer.domElement.releasePointerCapture(e.pointerId);
    if (p.node && this.mode === '2d') this.sim.dragEnd(p.node);
    this.renderer.domElement.style.cursor = this.hoveredId ? 'pointer' : 'default';
    if (p.moved) return;
    if (p.node) this.events.nodeClick?.(p.node.id);
    else this.events.stageClick?.();
  }

  private onWheel(e: WheelEvent): void {
    if (this.mode !== '2d') return;
    e.preventDefault();
    const [sx, sy] = this.local(e);
    const delta = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaMode === 2 ? e.deltaY * this.height : e.deltaY;
    const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, this.ortho.zoom * Math.exp(-delta * 0.0012)));
    const wx = this.worldX(sx), wy = this.worldY(sy);
    this.ortho.zoom = zoom;
    this.ortho.position.x = wx - (sx - this.width / 2) / zoom;
    this.ortho.position.y = wy + (sy - this.height / 2) / zoom;
    this.ortho.updateProjectionMatrix();
    this.userMoved = true;
    this.tween = null;
  }
}
