/** GLSL for the graph renderer. Nodes are point sprites shaded as soft discs; edges are 1 px lines
 *  with per-vertex color and alpha. Both end with Three's color-space conversion so hex colors
 *  (stored linear-light by THREE.Color) come out as authored. */

export const NODE_VERTEX = /* glsl */ `
attribute float size;
attribute vec3 color;
attribute float alpha;
attribute float ring;
uniform float uScale;
uniform float uPerspective;
varying vec3 vColor;
varying float vAlpha;
varying float vRing;

void main() {
  vColor = color;
  vAlpha = alpha;
  vRing = ring;
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  float px = size * uScale;
  if (uPerspective > 0.5) px = size * uScale / max(1.0, -mv.z);
  gl_PointSize = px * 2.0;
  gl_Position = projectionMatrix * mv;
}
`;

export const NODE_FRAGMENT = /* glsl */ `
varying vec3 vColor;
varying float vAlpha;
varying float vRing;

void main() {
  vec2 p = gl_PointCoord * 2.0 - 1.0;
  float d = length(p);
  if (d > 1.0) discard;
  float aa = fwidth(d) * 1.5;
  float disc = 1.0 - smoothstep(1.0 - aa, 1.0, d);
  if (vRing > 0.5) {
    // Annulus for hover/selection halos.
    float inner = smoothstep(0.70, 0.78 + aa, d);
    gl_FragColor = vec4(vColor, disc * inner * vAlpha);
  } else {
    // Soft lit disc: a touch brighter at the centre, a faint rim so overlaps stay readable.
    vec3 c = mix(vColor * 0.78, vColor * 1.12, 1.0 - d * d);
    float rim = smoothstep(0.80, 0.90, d) * (1.0 - smoothstep(0.94, 1.0, d));
    c = mix(c, vec3(1.0), rim * 0.14);
    gl_FragColor = vec4(c, disc * vAlpha);
  }
  #include <colorspace_fragment>
}
`;

export const LINE_VERTEX = /* glsl */ `
attribute vec3 color;
attribute float alpha;
varying vec3 vColor;
varying float vAlpha;

void main() {
  vColor = color;
  vAlpha = alpha;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

export const LINE_FRAGMENT = /* glsl */ `
varying vec3 vColor;
varying float vAlpha;

void main() {
  gl_FragColor = vec4(vColor, vAlpha);
  #include <colorspace_fragment>
}
`;
