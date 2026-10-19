// The background noise: its permutation table and its value distribution.
// The shader (shaders/perlin.glsl) evaluates the noise per pixel. Runs both
// in the browser and at build time (tables.js).

// Seeded Fisher–Yates shuffle of 0..255 (classic LCG, as in miniature-waffle).
export function buildPermutation(seed) {
  const perm = new Uint8Array(256);
  for (let i = 0; i < 256; i++) perm[i] = i;
  let s = seed;
  const rnd = () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
  for (let i = 255; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    const tmp = perm[i]; perm[i] = perm[j]; perm[j] = tmp;
  }
  return perm;
}

// Ken Perlin's improved noise, as in shaders/perlin.glsl, over permutation
// `perm`. Its values span exactly [−1, 1].
const fade = (t) => t * t * t * (t * (t * 6 - 15) + 10);
const lerp = (a, b, t) => a + (b - a) * t;
function grad(hash, x, y, z) {
  const h = hash & 15, u = h < 8 ? x : y, v = h < 4 ? y : h === 12 || h === 14 ? x : z;
  return ((h & 1) ? -u : u) + ((h & 2) ? -v : v);
}
export function perlin3(perm, px, py, pz) {
  const P = (i) => perm[i & 255];
  const X = Math.floor(px), Y = Math.floor(py), Z = Math.floor(pz);
  const x = px - X, y = py - Y, z = pz - Z, u = fade(x), v = fade(y), w = fade(z);
  const A = P(X) + Y, AA = P(A) + Z, AB = P(A + 1) + Z, B = P(X + 1) + Y, BA = P(B) + Z, BB = P(B + 1) + Z;
  return lerp(
    lerp(lerp(grad(P(AA), x, y, z), grad(P(BA), x - 1, y, z), u), lerp(grad(P(AB), x, y - 1, z), grad(P(BB), x - 1, y - 1, z), u), v),
    lerp(lerp(grad(P(AA + 1), x, y, z - 1), grad(P(BA + 1), x - 1, y, z - 1), u), lerp(grad(P(AB + 1), x, y - 1, z - 1), grad(P(BB + 1), x - 1, y - 1, z - 1), u), v),
    w);
}

// Steepest rate at which the noise changes with z: max |∂n/∂z| ≈ 3.09,
// measured over 8 million points and refined by local search.
export const MAX_DNDZ = 3.09;

// The noise's cumulative distribution, CDF(v) = share of the noise below v,
// at `bins` + 1 values evenly from −1 to 1. Measured from random points over
// the noise's whole period, averaged over several permutations, so it holds
// for any seed: across seeds it varies by about 0.01, far less than one
// view's own departure from it.
export function perlinCdf(bins = 1024, seeds = [1, 777, 4242, 31337], samples = 1e6) {
  const counts = new Float64Array(bins);
  for (const seed of seeds) {
    const perm = buildPermutation(seed);
    let s = seed;
    const rnd = () => (s = (s * 1103515245 + 12345) % 2147483648) / 2147483648;
    for (let i = 0; i < samples; i++) {
      const value = perlin3(perm, rnd() * 256, rnd() * 256, rnd() * 256);
      counts[Math.min(bins - 1, Math.floor(((value + 1) / 2) * bins))]++;
    }
  }
  const cdf = [0];
  let total = 0;
  for (const count of counts) cdf.push((total += count) / (seeds.length * samples));
  return cdf;
}

// The CDF's steepest slope, per unit of noise value: the density of the
// commonest value.
export function maxDensity(cdf) {
  const bins = cdf.length - 1;
  let density = 0;
  for (let i = 0; i < bins; i++) density = Math.max(density, ((cdf[i + 1] - cdf[i]) * bins) / 2);
  return density;
}
