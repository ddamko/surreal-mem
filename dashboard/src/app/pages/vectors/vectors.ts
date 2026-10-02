import { Component, DestroyRef, ElementRef, afterNextRender, computed, effect, inject, resource, signal, viewChild } from '@angular/core';
import { RouterLink } from '@angular/router';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { ApiService } from '../../core/api';
import { SpaceService } from '../../core/space';
import { BASE_TYPES, typeColor } from '../../core/types';
import { communityColor } from '../../core/graph-store';

interface Point {
  id: string;
  label: string;
  base_type: string;
  kind?: string;
  subject?: string;
  salience?: number;
  community?: number | null;
  projection: { x: number; y: number; x3: number; y3: number; z3: number };
}

@Component({
  selector: 'app-vectors',
  imports: [RouterLink],
  templateUrl: './vectors.html',
})
export class VectorsPage {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly space = inject(SpaceService);
  protected readonly typeColor = typeColor;
  protected readonly baseTypes = BASE_TYPES;
  private readonly canvas = viewChild.required<ElementRef<HTMLDivElement>>('canvas');

  protected readonly table = signal<'entity' | 'fact'>('entity');
  protected readonly colorBy = signal<'type' | 'community'>('type');
  protected readonly hovered = signal<Point | null>(null);
  protected readonly selected = signal<Point | null>(null);
  protected readonly filter = signal('');

  protected readonly points = resource({
    params: () => ({ space: this.space.param(), table: this.table() }),
    loader: async ({ params }) => {
      const { data, error } = await this.api.client.GET('/api/v1/projection', { params: { query: { space: params.space, table: params.table, limit: 8000 } } });
      if (error) throw error;
      return (data.rows as unknown as Point[]).filter((p) => p.projection && Number.isFinite(p.projection.x3));
    },
  });
  protected readonly count = computed(() => (this.points.hasValue() ? this.points.value().length : 0));
  protected readonly highlighted = computed(() => {
    const q = this.filter().trim().toLowerCase();
    if (!q || !this.points.hasValue()) return new Set<string>();
    return new Set(this.points.value().filter((p) => p.label.toLowerCase().includes(q)).map((p) => p.id));
  });

  private scene?: THREE.Scene;
  private cloud?: THREE.Points;
  private renderer?: THREE.WebGLRenderer;
  private camera?: THREE.PerspectiveCamera;
  private controls?: OrbitControls;
  private raycaster = new THREE.Raycaster();
  private pointer = new THREE.Vector2(2, 2);

  constructor() {
    afterNextRender(() => this.mount());
    effect(() => {
      this.points.hasValue();
      this.colorBy();
      this.highlighted();
      this.rebuild();
    });
  }

  private mount(): void {
    const el = this.canvas().nativeElement;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.domElement.style.display = 'block';
    el.appendChild(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(50, 1, 0.01, 1000);
    this.camera.position.set(0, 0, 28);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    const grid = new THREE.GridHelper(40, 20, 0x334155, 0x1e293b);
    grid.position.y = -12;
    (grid.material as THREE.Material).transparent = true;
    (grid.material as THREE.Material).opacity = 0.35;
    this.scene.add(grid);
    const resize = (): void => {
      const w = el.clientWidth, h = el.clientHeight;
      if (!w || !h) return;
      this.renderer!.setSize(w, h);
      this.camera!.aspect = w / Math.max(1, h);
      this.camera!.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(el);
    resize();
    el.addEventListener('pointermove', (e) => {
      const r = el.getBoundingClientRect();
      this.pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    });
    el.addEventListener('click', () => this.selected.set(this.hovered()));
    this.raycaster.params.Points = { threshold: 0.25 };
    let frame = 0;
    const tick = (): void => {
      frame = requestAnimationFrame(tick);
      if (!el.clientWidth || !el.clientHeight) return;
      this.controls?.update();
      this.pick();
      this.renderer!.render(this.scene!, this.camera!);
    };
    tick();
    this.rebuild();
    this.destroyRef.onDestroy(() => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      this.controls?.dispose();
      this.renderer?.dispose();
    });
  }

  private pick(): void {
    if (!this.cloud || !this.camera || !this.points.hasValue()) return;
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hit = this.raycaster.intersectObject(this.cloud)[0];
    const index = hit?.index;
    const next = index == null ? null : (this.points.value()[index] ?? null);
    if (next?.id !== this.hovered()?.id) this.hovered.set(next);
  }

  private rebuild(): void {
    if (!this.scene) return;
    if (this.cloud) {
      this.scene.remove(this.cloud);
      this.cloud.geometry.dispose();
      (this.cloud.material as THREE.Material).dispose();
      this.cloud = undefined;
    }
    const rows = this.points.hasValue() ? this.points.value() : [];
    if (!rows.length) return;
    const highlighted = this.highlighted();
    const scale = 2.2;
    const positions = new Float32Array(rows.length * 3);
    const colors = new Float32Array(rows.length * 3);
    const sizes = new Float32Array(rows.length);
    const cx = rows.reduce((s, p) => s + p.projection.x3, 0) / rows.length;
    const cy = rows.reduce((s, p) => s + p.projection.y3, 0) / rows.length;
    const cz = rows.reduce((s, p) => s + p.projection.z3, 0) / rows.length;
    rows.forEach((p, i) => {
      positions.set([(p.projection.x3 - cx) * scale, (p.projection.y3 - cy) * scale, (p.projection.z3 - cz) * scale], i * 3);
      const base = this.colorBy() === 'community' ? communityColor(p.community ?? -1) : typeColor(p.base_type);
      const c = new THREE.Color(base);
      if (highlighted.size && !highlighted.has(p.id)) c.multiplyScalar(0.25);
      colors.set([c.r, c.g, c.b], i * 3);
      sizes[i] = 0.25 + (p.salience ?? 0.5) * 0.35 + (highlighted.has(p.id) ? 0.3 : 0);
    });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    const material = new THREE.PointsMaterial({ size: 0.42, vertexColors: true, transparent: true, opacity: 0.95, sizeAttenuation: true });
    this.cloud = new THREE.Points(geometry, material);
    this.scene.add(this.cloud);
  }

  protected resetView(): void {
    this.camera?.position.set(0, 0, 28);
    this.controls?.target.set(0, 0, 0);
  }
}
