# NetSy visualizer

A self-contained TypeScript/Vite application for inspecting NetSy files. It reads CSV and
GeoPackage files locally in the browser; no data leaves the device.

## Development

Requires Node 23 through 26 because it uses `nicrainha`.

```sh
npm install
npm run dev     # binds to 0.0.0.0:5173, reachable from the local network
npm run build   # static site in dist/, with relative asset paths for GitHub Pages
npm run lint
```

## Views

Three views sit side by side; moving between them slides the interface and pans the
background with it.

- **Map** (the first view): a panel of map controls beside a panel holding the map in a
  white sheet. Drag a rectangle, which keeps the sheet's proportions, to zoom exactly into it; **Zoom out**
  and **Reset zoom** sit in the banner beside **Data**: Zoom out steps back out of one zoom,
  and Reset zoom shows everything again and forgets the zooms (each is gray when it has
  nothing to do). There is no panning, and geometry is always drawn exactly as it is in the
  file. **Lines** sets line width, which also sizes points. Colors are equalized over the features in view, and the legend
  labels its ticks with the values they stand for. **Data** moves to the data view.
- **Data**: every file NetSy reads or writes, as one bubble each, wired top to bottom by
  the `netsy synth` commands that make files from others. A file that is not loaded is gray;
  selecting it opens a file picker and loads the chosen file as that NetSy file, whatever
  it is called; while it loads, a rolling cat sits in the middle of the window and nothing
  else responds. Files are read and their map geometry prepared in a background worker.
  A loaded file is black; selecting it opens its table. **Map** moves back.
- **Table**: the file's rows in a white sheet, panned in any direction with the header
  pinned. **Remove** unloads the file and returns to the data view; **Data** returns
  without unloading it.

The map is ported from expert-succotash (`src/map`): every file's geometry is prepared
once into typed GPU buffers (polygons triangulated, lines split into segments, coordinates
relative to the data's center), so zooming only changes a transform. Lines are instanced
quads with round joins and points are discs with a black ring; nothing redraws unless the
data, the view or a control changes.

The graph and tables pan with nicrainha's model: drags follow the pointer, releases fling
with iOS's deceleration, and wheels, trackpads and arrow keys pan directly.

### The data graph

`src/circuit.ts` lays the graph out as a top-down circuit. Every bubble has the same size on
a grid of as many columns as fit the window; bubbles narrow a little where that lets all of
one command's inputs share a row. A file a command makes sits in the first row
below all of its inputs; a file nothing makes sits in the rows directly above the first
file made from it. Wires run only through the empty channels between rows and the gaps
between columns, so none crosses a bubble: outputs leave a bubble's bottom just right of its
middle, inputs arrive at its top just left of it, a file's inputs share one bus, and inputs
from further up drop through a column gap on lanes of their own.

## Glass

The interface uses nicolle's nicrainha engine (`src/engine`, `scripts/tables.js`;
attribution in `LICENSES/nicrainha.txt`): an endless, animated background at lightness 87,
seen through physical glass. Every `[data-glass]` element is a rounded-rectangle slab traced
per pixel with Snell's law, refracting at its edges and lightening toward white with its
thickness; panels are otherwise transparent. One corner radius, `--radius`, applies to all
glass, and panels pad their content by at least that radius so text sits on the glass's flat
middle. Overlapping panels follow page order. Glass inside a `[data-glass-clip]` region is
clipped to it and fades out over 36 px under its top edge, matched by a CSS mask on the
region's own content.

Data drawn on white (map colors and future table colors) uses nicrainha's default lightness,
L* 73.9124, independently of the scene's.

## Large tables and scenario files

Parquet decodes directly to column buffers: numeric typed arrays and
integer-coded string dictionaries. Workers transfer numeric buffers rather than
cloning a row object for every record. Maps scan columns, and table rows are
materialized only for the visible viewport. Speed and utilization maps display
trip-weighted means; additive counts and grams are summed.

The graph includes facility routing, parcel routing, powertrain/routing rules and
output indicators. Optional inputs are alternatives or extensions, not a claim
that every stage requires every displayed file. OMX remains a model input that
the browser does not decode.

Identifier columns in CSV remain text (including leading zeros). Parquet numeric
identifiers exceeding JavaScript's exact integer range are rejected rather than
silently rounded. Numeric table widths are bounded, so opening a large table
does not scan millions of formatted cells on the UI thread.
