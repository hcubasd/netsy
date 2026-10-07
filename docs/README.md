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

The diagram is a WebGL2 Perlin-noise backdrop using Nicrainha's default-lightness palette.
All data-bearing colors use the same color-science palette; interface chrome is grayscale.
