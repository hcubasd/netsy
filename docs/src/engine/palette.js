// The palette a lightness uses. Runs both in the browser and at build time
// (tables.js).
//
// nicrainha's 256 colors at a lightness are 256 points evenly around a
// circle, rounded to 8-bit sRGB. Toward L* 0 and 100 the circle shrinks, and
// neighbors round to the same color, down to a single color at the ends.
//
// A lightness uses the largest evenly spaced palette of unique colors: the
// largest n for which some rotation of nicrainha's n-gon,
// generatePalettes(n)[rotation], has n unique colors, and the first such
// rotation. Every n-gon is a subset of the 256-gon: rotation r takes
// vertices r + ⌊k · 256 / n⌋, k = 0…n − 1. So one call for the 256-gon,
// `ring` (256 RGB colors in vertex order), answers every n. Uniqueness isn't
// monotone in n, so n is scanned down from 256.
export function largestPalette(ring) {
  const color = ring.map(({ r, g, b }) => (r << 16) | (g << 8) | b);
  // Pairs of vertices with the same color.
  const pairs = [];
  for (let i = 0; i < 256; i++) for (let j = i + 1; j < 256; j++) if (color[i] === color[j]) pairs.push([i, j]);
  const taken = new Uint8Array(256);
  for (let n = 256; n > 1; n--) {
    for (let rotation = 0; rotation < 256; rotation++) {
      taken.fill(0);
      for (let k = 0; k < n; k++) taken[(rotation + Math.floor((k * 256) / n)) & 255] = 1;
      if (!pairs.some(([i, j]) => taken[i] && taken[j])) return { size: n, rotation };
    }
  }
  return { size: 1, rotation: 0 };
}
