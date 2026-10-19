// Build-time tables, served to the page as the virtual module
// "virtual:tables" (see vite.config.js). Runs in Node, never in the browser:
// they take a few seconds, and depend on nothing that varies per page load.
//
//   RGB        ROWS × 256 RGB triples, base64: row k is nicrainha's 256-gon,
//              in vertex order, at L* 100 · k / (ROWS − 1). Every lightness
//              shares the same 256 hue angles, so a vertex keeps its hue from
//              row to row, and the glass moves along a column of this table.
//   SIZES      each row's palette (palette.js): its size n,
//   ROTATIONS  and its rotation.
//   CDF        the noise's value distribution (noise.js).

import { generatePalettes } from "nicrainha";

import { perlinCdf } from "../src/engine/noise.js";
import { largestPalette } from "../src/engine/palette.js";

// 256 rows step L* by 100/255 ≈ 0.39: about one 8-bit sRGB level, so finer
// rows would mostly repeat colors.
export const ROWS = 256;

function buildRings() {
  const rgb = new Uint8Array(ROWS * 256 * 3);
  const palettes = [];
  for (let row = 0; row < ROWS; row++) {
    const ring = generatePalettes(256, { lightness: (100 * row) / (ROWS - 1) })[0];
    ring.forEach(({ r, g, b }, vertex) => rgb.set([r, g, b], (row * 256 + vertex) * 3));
    palettes.push(largestPalette(ring));
  }
  return { rgb, palettes };
}

// Vite plugin exposing the tables as an ES module.
export function tables() {
  const id = "virtual:tables";
  return {
    name: "tables",
    resolveId: (source) => (source === id ? `\0${id}` : null),
    load(resolved) {
      if (resolved !== `\0${id}`) return null;
      const { rgb, palettes } = buildRings();
      return [
        `export const ROWS = ${ROWS};`,
        `export const RGB = "${Buffer.from(rgb).toString("base64")}";`,
        `export const SIZES = ${JSON.stringify(palettes.map((p) => p.size))};`,
        `export const ROTATIONS = ${JSON.stringify(palettes.map((p) => p.rotation))};`,
        `export const CDF = ${JSON.stringify(perlinCdf().map((c) => +c.toFixed(6)))};`,
      ].join("\n");
    },
  };
}
