import { Component, DestroyRef, ElementRef, afterNextRender, inject } from '@angular/core';
import * as THREE from 'three';
import { LiveService } from '../../core/live';
import { themeColor } from '../../core/color';
import { typeColor } from '../../core/types';

/** A living field of memories: each arriving entity or fact becomes a point that drifts toward its
 *  type's region. Quiet by design; motion only answers new data (ADR-0031). */
@Component({
  selector: 'app-constellation',
  template: '',
  host: { class: 'block overflow-hidden' },
})
export class Constellation {
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly live = inject(LiveService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

  constructor() {
    afterNextRender(() => this.start());
  }

  private start(): void {
    const el = this.host.nativeElement;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    Object.assign(renderer.domElement.style, { display: 'block', width: '100%', height: '100%' });
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
    camera.position.set(0, 0, 18);

    const MAX = 1200;
    const positions = new Float32Array(MAX * 3);
    const colors = new Float32Array(MAX * 3);
    const targets: THREE.Vector3[] = [];
    const velocities: THREE.Vector3[] = [];
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geometry.setDrawRange(0, 0);
    const material = new THREE.PointsMaterial({ size: 0.16, vertexColors: true, transparent: true, opacity: 0.9, sizeAttenuation: true });
    const points = new THREE.Points(geometry, material);
    scene.add(points);
    let count = 0;

    const regions: Record<string, THREE.Vector3> = {
      person: new THREE.Vector3(-6, 1.5, 0),
      organization: new THREE.Vector3(-2, -2, 1),
      location: new THREE.Vector3(2, 2, -1),
      event: new THREE.Vector3(6, -1, 0),
      object: new THREE.Vector3(0, 3.5, 2),
      concept: new THREE.Vector3(3, -3.5, -2),
      fact: new THREE.Vector3(0, 0, 0),
    };

    const seed = (kind: string, color: THREE.Color): void => {
      const i = count < MAX ? count++ : Math.floor(Math.random() * MAX);
      const region = regions[kind] ?? regions['fact'];
      positions.set([(Math.random() - 0.5) * 30, 12, (Math.random() - 0.5) * 6], i * 3);
      colors.set([color.r, color.g, color.b], i * 3);
      targets[i] = region.clone().add(new THREE.Vector3((Math.random() - 0.5) * 3, (Math.random() - 0.5) * 2.5, (Math.random() - 0.5) * 3));
      velocities[i] = new THREE.Vector3();
      geometry.setDrawRange(0, Math.min(count, MAX));
    };

    // Prime with a faint background field so the page never looks empty.
    const ink = new THREE.Color(themeColor('--edge-ink', '#666666'));
    for (let i = 0; i < 160; i++) {
      const kinds = Object.keys(regions);
      seed(kinds[i % kinds.length], ink.clone().multiplyScalar(0.55));
    }
    for (let i = 0; i < count; i++) positions.set([targets[i].x, targets[i].y, targets[i].z], i * 3);

    const unsubscribe = this.live.on((event) => {
      if (event.action !== 'CREATE') return;
      if (event.table === 'entity') seed(String(event.record['base_type'] ?? 'concept'), new THREE.Color(typeColor(String(event.record['base_type'] ?? 'concept'))));
      else if (event.table === 'fact') seed('fact', new THREE.Color(themeColor('--color-primary', '#e8b04b')));
    });

    let needsResize = true;
    const resize = (): void => {
      needsResize = false;
      const { width: w, height: h } = el.getBoundingClientRect();
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / Math.max(1, h);
      camera.updateProjectionMatrix();
    };
    // Observer only flags; the frame loop resizes, so the callback never touches layout.
    const observer = new ResizeObserver(() => (needsResize = true));
    observer.observe(el);

    let frame = 0;
    const timer = new THREE.Timer();
    const tick = (now: number): void => {
      frame = requestAnimationFrame(tick);
      if (needsResize) resize();
      if (!el.clientWidth || !el.clientHeight) return;
      timer.update(now);
      const dt = Math.min(0.05, timer.getDelta());
      const t = timer.getElapsed();
      for (let i = 0; i < count; i++) {
        const target = targets[i];
        const v = velocities[i];
        const x = positions[i * 3], y = positions[i * 3 + 1], z = positions[i * 3 + 2];
        v.x += (target.x - x) * 2.2 * dt; v.y += (target.y - y) * 2.2 * dt; v.z += (target.z - z) * 2.2 * dt;
        v.multiplyScalar(0.9);
        positions[i * 3] = x + v.x * dt * 10 + (this.reduced ? 0 : Math.sin(t * 0.3 + i) * 0.0015);
        positions[i * 3 + 1] = y + v.y * dt * 10 + (this.reduced ? 0 : Math.cos(t * 0.2 + i * 0.7) * 0.0015);
        positions[i * 3 + 2] = z + v.z * dt * 10;
      }
      geometry.attributes['position'].needsUpdate = true;
      if (!this.reduced) points.rotation.y = Math.sin(t * 0.05) * 0.12;
      renderer.render(scene, camera);
    };
    tick(performance.now());

    this.destroyRef.onDestroy(() => {
      cancelAnimationFrame(frame);
      unsubscribe();
      observer.disconnect();
      geometry.dispose();
      material.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    });
  }
}
