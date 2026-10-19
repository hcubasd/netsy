// The page's one frame loop (NicrainhaScene drives it). Everything that moves
// content registers here and moves it in the frame the background is drawn,
// before the frame reads the glass panels' positions.

type Listener = (dt: number) => boolean

const listeners = new Set<Listener>()

// Registers `listener`, called every frame with the ms since the last one; it
// returns whether it moved anything. Returns the unregistering function.
export function onFrame(listener: Listener) {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

// Runs every listener, and returns whether any moved something.
export function advance(dt: number) {
  let moved = false
  for (const listener of listeners) moved = listener(dt) || moved
  return moved
}

// The window's position on the endless background, CSS px. A view whose
// content sits on the background (the pipeline graph) pans it.
export const background = { x: 0, y: 0 }
