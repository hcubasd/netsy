// The showcase's model on the page's side: every number the look depends on
// that isn't in the shaders, and the formulas the page needs. The
// background's lightness is the only input; all else is physics,
// measurement, or a design choice marked as such. See docs/README.md for
// the derivations.

// ── Background ──────────────────────────────────────────────────────────────

// Noise lattice cell, device px, for a window `width` × `height` device px:
// the long side spans 2 cells, unless that would make the short side span
// more than one. Whole pixels, so the noise's period, 256 cells, is too.
// Chosen by eye.
export const cellSize = (width, height) =>
  Math.max(1, Math.round(Math.max(Math.min(width, height), Math.max(width, height) / 2)));

// Depth the noise advances per second, in lattice units: the pattern turns
// over roughly every 10 s. Chosen by eye.
export const Z_PER_SECOND = 0.1;

// ── Glass ───────────────────────────────────────────────────────────────────

// Refractive index of glass. The air gap under a panel follows from it
// (glass.glsl).
export const IOR = 1.5;

// The panel, CSS px, shrunk to fit the window with this margin. Chosen by
// eye; it only sizes the flat middle.
export const PANEL = { width: 560, height: 320, margin: 24 };

// Corner radius, as a fraction of the largest a rounded rectangle allows
// (half its shorter side). It is also the glass's thickness over its flat
// middle, so it sets the air gap and the lightness too. Chosen by eye.
export const CORNER = 0.38;

// Glass length ℓ, in rem: the thickness that moves L* 1 − 1/e (63%) of the
// way from the background's to white. Chosen by eye.
export const GLASS_LENGTH_REM = 8;

// L* under glass `thickness` thick, in the same unit as `length` (ℓ): each
// layer of glass closes the same fraction of the remaining way to white.
// Must match glassLightness in color.glsl.
export const glassLightness = (lightness, thickness, length) =>
  100 - (100 - lightness) * Math.exp(-thickness / length);

// ── Text ────────────────────────────────────────────────────────────────────

// Relative luminance at which black and white text have equal WCAG contrast:
// (Y + 0.05) / 0.05 = 1.05 / (Y + 0.05), so Y = √(1.05 · 0.05) − 0.05 ≈
// 0.179, L* ≈ 49.4.
const EQUAL_CONTRAST_Y = Math.sqrt(1.05 * 0.05) - 0.05;

// "white" or "black", whichever has more contrast on L* `lightness`. Every
// color of a nicrainha palette has the palette's L*, hence the same
// luminance, so one answer holds for all of it.
export function textColor(lightness) {
  const Y = lightness > 8 ? ((lightness + 16) / 116) ** 3 : lightness / 903.3;
  return Y < EQUAL_CONTRAST_Y ? "white" : "black";
}
