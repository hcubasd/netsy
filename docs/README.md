# NetSy visualizer

This is a self-contained TypeScript/Vite application for inspecting NetSy synthesis files.
It parses CSV and GeoPackage files locally in the browser; no input data leaves the device.

## Development

Requires Node 23 through 26 because it uses `nicrainha`.

```sh
npm install
npm run dev
```

The development command binds Vite to `0.0.0.0`, making the app available to devices on
the local network. Use the displayed local-network URL to open it elsewhere.

```sh
npm run build
npm run lint
```

`npm run build` emits a portable static site to `dist/`, with relative asset paths suitable
for a GitHub Pages artifact deployment.

## Inputs

Drop any combination of NetSy CSV and GeoPackage files into the header. The map recognizes
the current core chain: zones with supply, demand, capacities, or needs; agents; desire
lines; road-network grades, loads, and emissions. It preserves the source CRS and requires
all loaded GeoPackage overlays to use the same CRS.

The visualizer uses a lightness-86 Nicrainha palette in a WebGL2 Perlin-noise scene.
Its ordinary interface panels are physical refractive glass: the shader moves their
background sample positions and lifts their colors toward white according to the local
glass thickness. A low-opacity white CSS overlay then adds a controllable backdrop blur
above the physical glass.

## Scene controls

The glass uses the Nicrainha focal-plane air gap (`4R/3` for glass with refractive index
`1.5`), derived from each panel's corner radius `R`. Its thickness similarly lifts the
selected background lightness exponentially toward `100`: `L = 100 - (100 - L_bg) e^(-h/l)`,
where `h` is the local glass thickness and `l` is an 8rem whitening length. A panel with
radius zero has neither gap nor lightness lift. All ordinary panels use the shared
`--radius` CSS custom property, so the same corner radius has the same material response
regardless of panel size.

Add `?blur=<pixels>` to set the CSS backdrop-blur radius on ordinary glass panels.
It defaults to `20`; `?blur=0` removes the CSS blur while retaining the physical glass.
Invalid or negative values use the default, and values above `64` are capped.

Add `?lightness=<0-100>` to set the CIE Lab lightness used by both the animated
background and NetSy's categorical and continuous palettes. Omit it to use Nicrainha's
default lightness of `86`; invalid values also use that default.
