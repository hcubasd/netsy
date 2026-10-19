import { generatePalettes } from "nicrainha";
import * as tables from "virtual:tables";

import { cellSize, IOR, Z_PER_SECOND } from "./model.js";
import { buildPermutation, MAX_DNDZ, maxDensity } from "./noise.js";
import { largestPalette } from "./palette.js";
import colorSource from "./shaders/color.glsl?raw";
import vertexSource from "./shaders/fullscreen.vert?raw";
import glassSource from "./shaders/glass.glsl?raw";
import perlinSource from "./shaders/perlin.glsl?raw";
import fragmentSource from "./shaders/scene.frag?raw";

// The showcase's renderer: a full-window canvas showing the endless
// background through glass panels. All the per-pixel work is in the fragment
// shader (shaders/scene.frag); this uploads its tables once and sets a few
// uniforms per frame. It takes everything in CSS px and works in device px.

// The noise repeats every 256 lattice units on every axis.
const PERIOD = 256;
// Must match MAX_PANELS in glass.glsl.
const MAX_PANELS = 160;

// Sets up WebGL on `canvas` for a background at L* `lightness`, and returns
// { draw, interval }:
//   draw(now, view) renders one frame of `view`: { pan, panels,
//     glassLength }, all CSS px. `pan` { x, y } is the window's position on
//     the endless background; each panel is { x, y, halfWidth, halfHeight,
//     radius }, (x, y) its center in the window; `glassLength` is ℓ.
//   interval is how often, in ms, the animation alone can change a pixel's
//     color: the time the noise's steepest pixel takes to cross one vertex
//     of the 256-gon, nicrainha's finest palette step.
export function createRenderer(canvas, lightness) {
  const gl = canvas.getContext("webgl2", { antialias: false, alpha: false });
  const uniform = createProgram(gl);
  const themeColor = uploadTables(gl, uniform, lightness);
  // A small data texture avoids fragment-uniform limits on mobile GPUs.
  const panelTexture = texture(gl, uniform.u_panels, 4, gl.RGBA32F, gl.RGBA, gl.FLOAT, null, MAX_PANELS, 3);
  const grid={texture:texture(gl,uniform.u_panelGrid,5,gl.RGBA16UI,gl.RGBA_INTEGER,gl.UNSIGNED_SHORT,new Uint16Array(4),1,1),cols:0,rows:0,data:new Uint16Array(0)};
  gl.uniform1f(uniform.u_ior, IOR);

  // One canvas pixel per device pixel: a canvas the browser rescales blends
  // colors.
  let deviceSize = null;
  const sizeObserver = observeDeviceSize(canvas, size => { deviceSize = size; });

  let dpr, cell, start, lastDpr;
  function resize(rect) {
    dpr = window.devicePixelRatio || 1;
    // ResizeObserver may still describe the previous orientation. Never use
    // its cached pixel size for a different CSS size or device-pixel ratio.
    const current=deviceSize&&Math.abs(deviceSize.cssWidth-rect.width)<.1&&Math.abs(deviceSize.cssHeight-rect.height)<.1&&deviceSize.dpr===dpr&&Math.abs(deviceSize.width-rect.width*dpr)<=1&&Math.abs(deviceSize.height-rect.height*dpr)<=1;
    const width=current?deviceSize.width:Math.round(rect.width*dpr);
    const height=current?deviceSize.height:Math.round(rect.height*dpr);
    if(width<=0||height<=0)return;
    if(width===canvas.width&&height===canvas.height&&cell&&lastDpr===dpr)return;
    lastDpr=dpr;
    canvas.width = width;
    canvas.height = height;
    gl.viewport(0, 0, width, height);
    gl.uniform2f(uniform.u_resolution, width, height);
    gl.uniform1f(uniform.u_fadeLength, 36 * dpr);
    gl.uniform1f(uniform.u_windowArea, width * height);
    cell = cellSize(width, height);
    gl.uniform1f(uniform.u_cell, cell);
    gl.uniform1i(uniform.u_period, PERIOD * cell);
  }

  // Pan and z are wrapped at the noise's period: seamless, and shader floats
  // stay small however far the view travels.
  function draw(now, { pan, panels, glassLength }) {
    start ??= now;
    const rect=canvas.getBoundingClientRect();
    if(rect.width<=0||rect.height<=0)return;
    resize(rect);
    setPanels(gl, uniform, panels, dpr, panelTexture, grid, rect);
    gl.uniform1f(uniform.u_glassLength, glassLength * dpr);
    gl.uniform2f(uniform.u_offset, wrap(pan.x * dpr, PERIOD * cell), wrap(pan.y * dpr, PERIOD * cell));
    gl.uniform1f(uniform.u_z, wrap(((now - start) / 1000) * Z_PER_SECOND, PERIOD));
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  const interval = 1000 / (256 * maxDensity(tables.CDF) * MAX_DNDZ * Z_PER_SECOND);
  return { draw, interval, themeColor, dispose: () => sizeObserver.disconnect() };
}

const wrap = (value, period) => ((value % period) + period) % period;

// Compiles the fullscreen-triangle program, resolving the fragment shader's
// #include lines, makes it current, and returns its uniform locations by
// name.
function createProgram(gl) {
  const includes = { "perlin.glsl": perlinSource, "glass.glsl": glassSource, "color.glsl": colorSource };
  function compile(type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
    return shader;
  }
  const program = gl.createProgram();
  gl.attachShader(program, compile(gl.VERTEX_SHADER, vertexSource));
  gl.attachShader(program, compile(gl.FRAGMENT_SHADER, fragmentSource.replace(/^#include "(.+)"$/gm, (_, name) => includes[name])));
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
  gl.useProgram(program);
  gl.bindVertexArray(gl.createVertexArray());
  const uniform = {};
  for (let i = 0; i < gl.getProgramParameter(program, gl.ACTIVE_UNIFORMS); i++) {
    const name = gl.getActiveUniform(program, i).name.replace(/\[0\]$/, "");
    uniform[name] = gl.getUniformLocation(program, name);
  }
  return uniform;
}

// Uploads the lookup tables (tables.js), each with one last row for the
// background's own lightness, computed here by nicrainha at exactly
// `lightness`:
//   u_perm     the noise permutation, seeded at random,
//   u_palette  nicrainha's 256-gon at L* 0…100, then at `lightness`,
//   u_ngons    each of those rows' palette: its size n, then its rotation,
//   u_cdf      the noise's value distribution,
// and picks a random shift around the circle, u_shift. Seed and shift make
// each page load a different view of the same background.
function uploadTables(gl, uniform, lightness) {
  const ring = generatePalettes(256, { lightness })[0];
  const own = largestPalette(ring);

  const rgb = Uint8Array.from(atob(tables.RGB), (c) => c.charCodeAt(0));
  const palette = new Uint8Array(rgb.length + 256 * 3);
  palette.set(rgb);
  palette.set(ring.flatMap(({ r, g, b }) => [r, g, b]), rgb.length);
  const ngons = new Uint16Array([...tables.SIZES, own.size, ...tables.ROTATIONS, own.rotation]);

  texture(gl, uniform.u_perm, 0, gl.R8UI, gl.RED_INTEGER, gl.UNSIGNED_BYTE, buildPermutation(Math.floor(Math.random() * 99999)), 256, 1);
  texture(gl, uniform.u_palette, 1, gl.RGB8, gl.RGB, gl.UNSIGNED_BYTE, palette, 256, tables.ROWS + 1);
  texture(gl, uniform.u_ngons, 2, gl.R16UI, gl.RED_INTEGER, gl.UNSIGNED_SHORT, ngons, tables.ROWS + 1, 2);
  texture(gl, uniform.u_cdf, 3, gl.R32F, gl.RED, gl.FLOAT, new Float32Array(tables.CDF), tables.CDF.length, 1);
  gl.uniform1f(uniform.u_lightness, lightness);
  const shift = Math.floor(Math.random() * 256);
  gl.uniform1i(uniform.u_shift, shift);
  const color = ring[(128 + shift) & 255];
  return `rgb(${color.r} ${color.g} ${color.b})`;
}

// A nearest-filtered lookup texture, `width` × `height`, bound to sampler
// `location` on texture unit `unit`.
function texture(gl, location, unit, internalFormat, format, type, data, width, height) {
  gl.activeTexture(gl.TEXTURE0 + unit);
  const result = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, result);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
  gl.texImage2D(gl.TEXTURE_2D, 0, internalFormat, width, height, 0, format, type, data);
  gl.uniform1i(location, unit);
  return result;
}

// Calls back with the canvas's exact size in device pixels whenever it
// changes. At fractional pixel ratios, rounding CSS px × devicePixelRatio
// can miss by one, so the browser's own device-pixel size is used where it
// reports it (not Safari), and the rounding elsewhere.
function observeDeviceSize(canvas, callback) {
  const observer = new ResizeObserver(([entry]) => {
    const exact = entry.devicePixelContentBoxSize?.[0];
    const dpr = window.devicePixelRatio || 1;
    callback({width:exact?exact.inlineSize:Math.round(entry.contentRect.width*dpr),
      height:exact?exact.blockSize:Math.round(entry.contentRect.height*dpr),
      cssWidth:entry.contentRect.width,cssHeight:entry.contentRect.height,dpr});
  });
  try {
    observer.observe(canvas, { box: "device-pixel-content-box" });
  } catch {
    observer.observe(canvas);
  }
  return observer;
}

// Visible glass data: box, clip and radius rows, all in device pixels.
const panelData = new Float32Array(4 * MAX_PANELS * 3);
function setPanels(gl, uniform, panels, dpr, panelTexture, grid, origin) {
  // Each screen tile lists only glass whose bounds touch it. Wide screens
  // do not require scanning every island for every background pixel.
  const tile=128*dpr,cols=Math.ceil(gl.drawingBufferWidth/tile),rows=Math.ceil(gl.drawingBufferHeight/tile);
  const resized=grid.cols!==cols||grid.rows!==rows;
  if(resized){grid.cols=cols;grid.rows=rows;grid.data=new Uint16Array(cols*rows*16);}else grid.data.fill(0);
  if (panels.length > MAX_PANELS) throw new Error("Too many visible glass panels");
  const count = panels.length;
  for (let i = 0; i < count; i++) {
    const {halfWidth,halfHeight,radius}=panels[i];
    const x=panels[i].x-origin.left,y=panels[i].y-origin.top;
    panelData.set([x*dpr,y*dpr,halfWidth*dpr,halfHeight*dpr],4*i);
    const source=panels[i].clip;
    const clip=source?{x:source.x-origin.left,y:source.y-origin.top,width:source.width,height:source.height}:{x:0,y:0,width:1e6,height:1e6};
    panelData.set([clip.x*dpr,clip.y*dpr,(clip.x+clip.width)*dpr,(clip.y+clip.height)*dpr],4*(MAX_PANELS+i));
    panelData[4*(2*MAX_PANELS+i)]=radius*dpr;
    const left=Math.max(0,x-halfWidth,clip.x),right=Math.min(gl.drawingBufferWidth/dpr,x+halfWidth,clip.x+clip.width);
    const top=Math.max(0,y-halfHeight,clip.y),bottom=Math.min(gl.drawingBufferHeight/dpr,y+halfHeight,clip.y+clip.height);
    if(left>=right||top>=bottom)continue;
    for(let gy=Math.floor(top/128);gy<=Math.min(rows-1,Math.floor(bottom/128));gy++)for(let gx=Math.floor(left/128);gx<=Math.min(cols-1,Math.floor(right/128));gx++){
      const offset=(gy*cols+gx)*16,n=grid.data[offset];
      if(n===65535)continue;
      if(n===15){grid.data[offset]=65535;continue;}
      grid.data[offset+1+n]=i;grid.data[offset]=n+1;
    }
  }
  gl.activeTexture(gl.TEXTURE4);gl.bindTexture(gl.TEXTURE_2D,panelTexture);
  gl.texSubImage2D(gl.TEXTURE_2D,0,0,0,MAX_PANELS,3,gl.RGBA,gl.FLOAT,panelData);
  gl.uniform1i(uniform.u_panelCount,count);
  gl.activeTexture(gl.TEXTURE5);gl.bindTexture(gl.TEXTURE_2D,grid.texture);
  if(resized)gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA16UI,cols*4,rows,0,gl.RGBA_INTEGER,gl.UNSIGNED_SHORT,grid.data);
  else gl.texSubImage2D(gl.TEXTURE_2D,0,0,0,cols*4,rows,gl.RGBA_INTEGER,gl.UNSIGNED_SHORT,grid.data);
  gl.uniform2i(uniform.u_gridSize,cols,rows);gl.uniform1f(uniform.u_tile,tile);
}
