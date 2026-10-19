// Ported from expert-succotash (src/lib/equalize.ts).

// Histogram equalization: place a value by its percentile rank in the
// observed distribution rather than by its linear position between the
// minimum and the maximum.
//
// The ramp has a fixed number of colors, and spending them evenly across the
// value range wastes almost all of them whenever the data is skewed -- which
// accumulated flow always is, since most of any scene is lightly crossed and
// a thin tail is heavily crossed. Ranking by percentile spends the colors
// where the data actually is: a crowded band of values gets proportionally
// more of the ramp, a sparse one gets less.
//
// The cost is that the middle of the ramp stops meaning "the middle of the
// range" and starts meaning "the median observation", so a legend can no
// longer place its ticks at even intervals -- see valueAt, which is what
// lets a legend label its ticks with the values they actually stand for.

export type Equalizer = {
  // value -> [0,1] percentile rank
  at: (value: number) => number;
  // [0,1] -> the value at that percentile, for legend ticks
  valueAt: (t: number) => number;
  min: number;
  max: number;
  count: number;
};

// Index of the first element >= value ("searchsorted left"). Ties therefore
// all resolve to the same rank, which matters: equal data must never be
// split across different colors just because it appears more than once.
function lowerBound(sorted: Float64Array, value: number): number {
  let lo = 0;
  let hi = sorted.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (sorted[mid] < value) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

export function equalize(values: ArrayLike<number>): Equalizer {
  const finite: number[] = [];
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (Number.isFinite(v)) finite.push(v);
  }

  if (finite.length === 0) {
    return { at: () => 0, valueAt: () => 0, min: 0, max: 0, count: 0 };
  }

  const sorted = Float64Array.from(finite).sort();
  const n = sorted.length;
  const min = sorted[0];
  const max = sorted[n - 1];

  // A single distinct value has no distribution to equalize against; putting
  // it at the bottom of the ramp rather than an arbitrary middle keeps the
  // legend honest about there being nothing to compare.
  if (n === 1 || min === max) {
    return { at: () => 0, valueAt: () => min, min, max, count: n };
  }

  return {
    at: (value: number) => (Number.isFinite(value) ? lowerBound(sorted, value) / (n - 1) : 0),
    valueAt: (t: number) => sorted[Math.min(n - 1, Math.max(0, Math.round(t * (n - 1))))],
    min,
    max,
    count: n,
  };
}
