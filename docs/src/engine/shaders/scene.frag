#version 300 es
// The showcase's pixels: an endless, pannable nicrainha background, seen
// through floating glass panels.
//
// Runs once per device pixel, every frame, at full resolution:
//   1. trace the pixel's view ray back through the glass to the point of the
//      background it sees (glass.glsl),
//   2. evaluate one octave of Perlin noise there (perlin.glsl),
//   3. color it: the value's palette band, dithered, at the lightness the
//      glass moves it to (color.glsl).
// See docs/README.md for the model and its derivations.

precision highp float;
precision highp int;
precision highp usampler2D;

uniform vec2 u_offset;  // the window's position on the background, device px,
                        // within one period of the noise
uniform float u_cell;   // noise lattice cell, device px
uniform int u_period;   // the noise's period, 256 cells, device px
uniform float u_z;      // noise depth: the animation time

out vec4 outColor;

#include "perlin.glsl"
#include "glass.glsl"
#include "color.glsl"

void main() {
  vec2 pixel = vec2(gl_FragCoord.x, u_resolution.y - gl_FragCoord.y);
  float thickness, fade;
  vec2 point = seenPoint(pixel, thickness, fade);
  float value = perlin3(vec3(mod((point + u_offset) / u_cell, 256.0), u_z));
  // The pixel's own spot on the background picks its dither draw: the grain
  // pans with the background, and the glass doesn't stretch it.
  ivec2 spot = ivec2(mod(floor(pixel + u_offset), float(u_period)));
  outColor = paletteColor(value, glassLightness(thickness), spot);
  if (fade < 1.0) {
    float plain = perlin3(vec3(mod((pixel + u_offset) / u_cell, 256.0), u_z));
    outColor = mix(paletteColor(plain, glassLightness(0.0), spot), outColor, fade);
  }
}
