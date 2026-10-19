// The glass: rounded-rectangle panels floating above the background, and the
// ray tracer through them. Included by scene.frag (renderer.js resolves
// #include). See docs/README.md for the model and its derivations.
//
// Coordinates are device px from the window's top-left, y down, z up toward
// the viewer. The background is an endless floor, z = 0, and the viewer
// looks straight down.

uniform float u_fadeLength;
uniform vec2 u_resolution;                // the window, device px
const int MAX_PANELS = 160;                // must match renderer.js
uniform int u_panelCount;
uniform sampler2D u_panels;
uniform usampler2D u_panelGrid;
uniform ivec2 u_gridSize;
uniform float u_tile;
vec4 panelBox(int i) {return texelFetch(u_panels, ivec2(i, 0), 0);}
vec4 panelClip(int i) {return texelFetch(u_panels, ivec2(i, 1), 0);}
float panelRadius(int i) {return texelFetch(u_panels, ivec2(i, 2), 0).x;}
uniform float u_ior;                      // refractive index of the glass

// ── Panel ───────────────────────────────────────────────────────────────────
// A panel is a solid whose flat bottom floats at height D (the air gap) and
// whose top is every point at distance R from an inner rectangle (half-size
// panel − R) lying at z = D: flat in the middle, quarter-cylinders along the
// edges, eighth-spheres at the corners. It is convex. Positions below are
// relative to its center.

struct Panel {
  vec2 center;
  vec2 halfSize;
  float radius;  // R: the corner radius, and the glass's thickness over its flat middle
  float gap;     // D: the background lies in the edge lens's focal plane,
                 // D = (1/(n − 1) − 1/n) · R
};

Panel panelAt(int i) {
  float radius = panelRadius(i);
  return Panel(panelBox(i).xy, panelBox(i).zw, radius, (1.0 / (u_ior - 1.0) - 1.0 / u_ior) * radius);
}

// Horizontal offset from the inner rectangle: zero over it, otherwise the
// vector from its nearest point.
vec2 offsetFromInner(Panel panel, vec2 xy) {
  return sign(xy) * max(abs(xy) - (panel.halfSize - panel.radius), 0.0);
}

// Thickness of the glass over `xy`: R over the flat middle, falling to 0 at
// the rim and outside.
float thicknessAt(Panel panel, vec2 xy) {
  float s = length(offsetFromInner(panel, xy));
  return s < panel.radius ? sqrt(panel.radius * panel.radius - s * s) : 0.0;
}

// Signed distances to the curved top and to the flat bottom; negative inside.
float distanceToTop(Panel panel, vec3 p) {
  return length(vec3(offsetFromInner(panel, p.xy), p.z - panel.gap)) - panel.radius;
}
float distanceToBottom(Panel panel, vec3 p) { return panel.gap - p.z; }

// Outward unit normal at a surface point: whichever surface it lies on.
vec3 surfaceNormal(Panel panel, vec3 p) {
  if (distanceToBottom(panel, p) > distanceToTop(panel, p)) return vec3(0.0, 0.0, -1.0);
  return normalize(vec3(offsetFromInner(panel, p.xy), p.z - panel.gap));
}

// ── Tracing ─────────────────────────────────────────────────────────────────

// Iteration limits. Rays grazing the rim need many small steps and several
// reflections; at these limits none runs out in practice.
const int MAX_STEPS = 512;
const int MAX_BOUNCES = 64;

// Distance along `dir` from `origin`, inside the glass, to its surface, by
// sphere tracing the solid's signed distance, max(top, bottom): a lower
// bound on the true distance, which is all marching needs.
float distanceToSurface(Panel panel, vec3 origin, vec3 dir) {
  float t = 1e-2;
  for (int i = 0; i < MAX_STEPS; i++) {
    vec3 p = origin + t * dir;
    float d = -max(distanceToTop(panel, p), distanceToBottom(panel, p));
    if (d < 1e-3) break;
    t += max(d, 1e-3);
  }
  return t;
}

// Follows a ray that has just entered the glass at `pos` heading `dir` to
// where, and in which direction, it leaves. It refracts out where Snell's
// law allows and reflects (total internal reflection) where it doesn't. The
// glass is convex, so a ray that has left never comes back.
void traceGlass(Panel panel, inout vec3 pos, inout vec3 dir) {
  for (int bounce = 0; bounce < MAX_BOUNCES; bounce++) {
    pos += distanceToSurface(panel, pos, dir) * dir;
    vec3 normal = surfaceNormal(panel, pos);
    vec3 exitDir = refract(dir, -normal, u_ior);  // glass → air
    if (exitDir != vec3(0.0)) {
      dir = exitDir;
      return;
    }
    dir = reflect(dir, normal);
  }
}

// Where a ray from `pos` heading `dir`, in window coordinates, meets the
// scene. Heading down, it lands on the floor wherever that is, on screen or
// off. Heading up, it never reaches the floor: it takes the window's edge
// pixel where its horizontal path crosses the window's border, as if each
// edge pixel continued straight up as a wall.
vec2 hitScene(vec3 pos, vec3 dir) {
  if (dir.z < 0.0) return pos.xy + dir.xy * (pos.z / -dir.z);
  // The window, by the centers of its outermost pixels.
  vec2 lo = vec2(0.5), hi = u_resolution - 0.5;
  vec2 toWall = vec2(
    dir.x > 0.0 ? (hi.x - pos.x) / dir.x : dir.x < 0.0 ? (lo.x - pos.x) / dir.x : 1e30,
    dir.y > 0.0 ? (hi.y - pos.y) / dir.y : dir.y < 0.0 ? (lo.y - pos.y) / dir.y : 1e30);
  float t = min(toWall.x, toWall.y);
  if (t >= 1e30) t = 0.0;  // straight up: the wall it is already against
  return clamp(pos.xy + t * dir.xy, lo, hi);
}

// The point of the scene the viewer sees at `pixel`, and the thickness of the
// glass above it (0 off the glass). A pixel is traced through at most one
// panel: the last submitted visible panel, matching the UI stacking order.
vec2 seenPoint(vec2 pixel, out float thickness, out float fade) {
  fade = 1.0;
  thickness = 0.0;
  int chosen = -1;
  ivec2 tile = clamp(ivec2(pixel / u_tile), ivec2(0), u_gridSize - 1);
  int count = int(texelFetch(u_panelGrid, ivec2(tile.x * 4, tile.y), 0).x);
  for (int slot = 0; slot < MAX_PANELS; slot++) {
    int i = slot;
    if (count != 65535) {
      if (slot >= count) break;
      uvec4 entries = texelFetch(u_panelGrid, ivec2(tile.x * 4 + (slot + 1) / 4, tile.y), 0);
      i = int(entries[(slot + 1) % 4]);
    }
    if (i >= u_panelCount) break;
    vec4 clip = panelClip(i);
    if (any(lessThan(pixel,clip.xy)) || any(greaterThan(pixel,clip.zw))) continue;
    if (any(greaterThan(abs(pixel-panelBox(i).xy),panelBox(i).zw))) continue;
    Panel panel = panelAt(i);
    float h = thicknessAt(panel, pixel - panel.center);
    if (h > 0.0) { thickness = h; chosen = i; }
  }
  if (chosen < 0) return pixel;

  // Only clipped world glass fades into the top navigation banner.
  if (panelClip(chosen).w - panelClip(chosen).y < 1e5)
    fade = smoothstep(0.0, u_fadeLength, pixel.y - panelClip(chosen).y);
  Panel panel = panelAt(chosen);
  vec2 xy = pixel - panel.center;
  // The view ray comes straight down and refracts into the top surface.
  vec3 pos = vec3(xy, panel.gap + thickness);
  vec3 normal = vec3(offsetFromInner(panel, xy), thickness) / panel.radius;
  vec3 dir = refract(vec3(0.0, 0.0, -1.0), normal, 1.0 / u_ior);  // air → glass
  traceGlass(panel, pos, dir);
  return hitScene(pos + vec3(panel.center, 0.0), dir);
}
