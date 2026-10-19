// Ported from expert-succotash (src/gl/shaders.ts): fills, thick lines and
// discs.

const TRANSFORM = `
  uniform vec2 u_center;
  uniform vec2 u_scale;
  vec2 toClip(vec2 world) {
    return (world - u_center) * u_scale;
  }
`;

// Flat colored geometry: zone fill triangles, zone borders, and network
// links all share this. Every line in the app is now a plain gl.LINES at the
// spec-guaranteed width of 1 -- the only width gl.lineWidth is required to
// support, and the width the accumulation model actually prefers, since a
// thicker stroke manufactures crossings between lines that merely pass near
// each other.
export const FLAT_VERT = `#version 300 es
  in vec2 a_position;
  in vec3 a_color;
  out vec3 v_color;
  ${TRANSFORM}
  void main() {
    v_color = a_color;
    gl_Position = vec4(toClip(a_position), 0.0, 1.0);
  }
`;

export const FLAT_FRAG = `#version 300 es
  precision highp float;
  in vec3 v_color;
  out vec4 outColor;
  void main() {
    outColor = vec4(v_color, 1.0);
  }
`;

// Network links, as quads rather than gl.LINES. gl.lineWidth is required to
// support exactly one width -- 1.0 -- and every ANGLE-backed browser reports
// exactly that range, so any stroke thicker than a hairline has to be
// triangulated. This is the same instancing shape the agents use: one unit
// quad per link, stretched along it and extruded across it.
//
// The extrusion happens in pixel space rather than clip space. Clip space is
// not isotropic in general -- a fixed clip-space offset would be a different
// number of pixels horizontally than vertically -- so the endpoints are
// converted to pixels, offset perpendicular there, and converted back. That
// keeps a 2px road 2px wide whatever direction it runs.
export const THICK_VERT = `#version 300 es
  in vec2 a_corner;
  in vec4 a_endpoints;
  in vec3 a_color;
  uniform vec2 u_viewportPx;
  uniform float u_halfWidthPx;
  out vec3 v_color;
  ${TRANSFORM}
  void main() {
    v_color = a_color;
    // Not named "half": that is a reserved word in GLSL ES and fails to
    // compile.
    vec2 halfViewport = u_viewportPx * 0.5;
    vec2 p0 = toClip(a_endpoints.xy) * halfViewport;
    vec2 p1 = toClip(a_endpoints.zw) * halfViewport;

    vec2 delta = p1 - p0;
    float span = length(delta);
    // A zero-length link would make normalize produce NaN and take the whole
    // quad with it, so it falls back to an arbitrary direction and collapses
    // into an invisible sliver instead.
    vec2 direction = span > 1e-6 ? delta / span : vec2(1.0, 0.0);
    vec2 normal = vec2(-direction.y, direction.x);

    vec2 pixel = mix(p0, p1, a_corner.x) + normal * (a_corner.y * u_halfWidthPx);
    gl_Position = vec4(pixel / halfViewport, 0.0, 1.0);
  }
`;

export const THICK_FRAG = `#version 300 es
  precision highp float;
  in vec3 v_color;
  out vec4 outColor;
  void main() {
    outColor = vec4(v_color, 1.0);
  }
`;

// Agents: one unit quad instanced per point, at a single radius shared by
// every agent on screen. Instancing rather than gl.POINTS because
// gl_PointSize has an implementation-defined ceiling that varies by driver.
//
// The radius is uniform, so identical data always draws at the same size.
export const POINT_VERT = `#version 300 es
  in vec2 a_corner;
  in vec2 a_position;
  in vec3 a_color;
  uniform vec2 u_pixelRadius;
  out vec3 v_color;
  out vec2 v_corner;
  ${TRANSFORM}
  void main() {
    v_color = a_color;
    v_corner = a_corner;
    gl_Position = vec4(toClip(a_position) + a_corner * u_pixelRadius, 0.0, 1.0);
  }
`;

// The quad is sized to the *outer* edge -- fill radius plus border, when
// there is one -- so a_corner covers the whole disc including its ring.
// u_innerRatio is where the fill stops and the border starts, as a fraction
// of that outer radius: 1.0 draws no border band at all (the joins' case,
// which share this shader but never get one), anything less carves a black
// ring off the edge inward.
export const POINT_FRAG = `#version 300 es
  precision highp float;
  in vec3 v_color;
  in vec2 v_corner;
  uniform float u_radiusPx;
  uniform float u_innerRatio;
  out vec4 outColor;
  void main() {
    // Round the quad off into a disc -- but only once there is enough of it
    // to round. The shader runs at the pixel centre, so the test asks
    // "is this pixel's centre inside the circle", and at a one-pixel mark
    // that is decided by where the mark happens to fall relative to the
    // pixel grid rather than by anything real: about a fifth of them land
    // in a corner and vanish outright, and the rest lose most of their
    // coverage. Below a two-pixel diameter the quad is left square, which
    // at that size is indistinguishable from a disc anyway and is the only
    // version that reliably puts ink down.
    float d2 = dot(v_corner, v_corner);
    if (u_radiusPx > 1.0 && d2 > 1.0) discard;
    outColor = d2 > u_innerRatio * u_innerRatio ? vec4(0.0, 0.0, 0.0, 1.0) : vec4(v_color, 1.0);
  }
`;
