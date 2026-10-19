// A pixel's color: the palette band a noise value falls in, dithered, at the
// lightness the glass moves it to. Every pixel is exactly a nicrainha color.
// Included by scene.frag (renderer.js resolves #include). See
// docs/README.md for the model and its derivations.

const int TABLE_ROWS = 256;            // must match tables.js
uniform sampler2D u_palette;           // nicrainha's 256-gon, 256 vertices × (TABLE_ROWS + 1)
                                       // rows: L* 0…100 evenly, then the background's own,
                                       // at its exact lightness
uniform highp usampler2D u_ngons;      // each row's palette, (TABLE_ROWS + 1) × 2: its
                                       // size n, then its rotation
uniform highp sampler2D u_cdf;         // the noise's CDF at values −1…1 evenly
uniform int u_shift;                   // random per load: where on the circle the noise starts
uniform float u_lightness;             // the background's L*
uniform float u_glassLength;           // ℓ, device px
uniform float u_windowArea;            // device px

// ── Lightness ───────────────────────────────────────────────────────────────

// L* under glass `thickness` thick: each layer of glass closes the same
// fraction of the remaining way to white, 1 − 1/e of it per ℓ.
float glassLightness(float thickness) {
  return 100.0 - (100.0 - u_lightness) * exp(-thickness / u_glassLength);
}

// The palette row for L* `lightness`: the nearest table row, or, within half
// a row of the background's own L*, the background's own ring, so the glass
// meets the background seamlessly at its rim.
int rowFor(float lightness) {
  float rowStep = 100.0 / float(TABLE_ROWS - 1);
  if (abs(lightness - u_lightness) < rowStep / 2.0) return TABLE_ROWS;
  return int(floor(lightness / rowStep + 0.5));
}

// ── Band ────────────────────────────────────────────────────────────────────

// Where noise `value` falls once around the circle, in [0, 1): its share of
// the noise below it, so every part of the circle covers the same share of
// the background, shifted by u_shift.
float positionOf(float value) {
  float bins = float(textureSize(u_cdf, 0).x - 1);
  float b = clamp((value + 1.0) * 0.5, 0.0, 1.0) * bins;
  int i = min(int(b), int(bins) - 1);
  float share = mix(texelFetch(u_cdf, ivec2(i, 0), 0).r, texelFetch(u_cdf, ivec2(i + 1, 0), 0).r, b - float(i));
  return fract(share + float(u_shift) / 256.0);
}

// ── Dither ──────────────────────────────────────────────────────────────────

// PCG2D hash (Jarzynski & Olano 2020).
uvec2 pcg2d(uvec2 v) {
  v = v * 1664525u + 1013904223u;
  v.x += v.y * 1664525u; v.y += v.x * 1664525u;
  v ^= v >> 16u;
  v.x += v.y * 1664525u; v.y += v.x * 1664525u;
  v ^= v >> 16u;
  return v;
}

// How many colors past its band a pixel shows, for a palette of `n` colors:
// each color covers 1/n of the background, an expected area A = window / n,
// and the dither reaches w = ln A colors ahead, j = 0…w − 1, drawn from a
// right-triangular distribution, so the nearer colors are the likelier. The
// draw is fixed per spot of the background, `spot`.
int ditherOffset(int n, ivec2 spot) {
  float w = log(max(u_windowArea / float(n), 1.0));
  float u = (float(pcg2d(uvec2(spot)).x) + 0.5) / 4294967296.0;
  return int(floor(w * (1.0 - sqrt(u))));
}

// ── Color ───────────────────────────────────────────────────────────────────

// The color for noise `value` at L* `lightness`, dithered by the background
// spot `spot`. The row's palette is nicrainha's n-gon at the row's rotation
// r, vertices r + ⌊k · 256 / n⌋; color k, the band, spans the positions
// from its vertex to the next. The pixel shows the band's color plus its
// dither offset, around the circle.
vec4 paletteColor(float value, float lightness, ivec2 spot) {
  int row = rowFor(lightness);
  int n = int(texelFetch(u_ngons, ivec2(row, 0), 0).r);
  int r = int(texelFetch(u_ngons, ivec2(row, 1), 0).r);
  // Position on the 256-gon from the rotation's first vertex, and its band:
  // the last k with ⌊k · 256 / n⌋ ≤ y, k = ⌈(⌊y⌋ + 1) · n / 256⌉ − 1.
  int y = int(mod(positionOf(value) * 256.0 - float(r), 256.0)) & 255;
  int k = ((y + 1) * n + 255) / 256 - 1;
  int c = (k + ditherOffset(n, spot)) % n;
  return texelFetch(u_palette, ivec2((r + (c * 256) / n) & 255, row), 0);
}
