// Panning, as in nicrainha's showcase: drags follow the pointer exactly,
// releases fling with iOS's deceleration and Android's velocity tracking, and
// wheels and trackpads pan directly (trackpads add their own momentum). The
// page moves content itself in the frame it draws, so content and the
// background never lag each other.
//
// Unlike the showcase, a pan surface also holds clickable content: a drag
// only starts once the pointer has travelled DRAG_SLOP, and the click that
// ends a drag is swallowed. A surface may be bounded (a table) or endless
// (the pipeline graph).

// Fling deceleration: velocity is multiplied by this every millisecond.
// iOS's own scroll deceleration (UIScrollView.DecelerationRate.normal).
const DECELERATION = 0.998
// Release velocity is measured over the pointer's last 100 ms, and is zero if
// it rested 40 ms before release: Android's VelocityTracker horizon and its
// "pointer stopped" time.
const VELOCITY_WINDOW = 100
const STOPPED_TIME = 40
// CSS px a pointer travels before a press becomes a drag (Android's touch
// slop is 8 dp; a mouse needs less).
const DRAG_SLOP = { mouse: 4, touch: 8 }
// CSS px an arrow key pans.
const KEY_STEP = 48

export interface Bounds {
  minX: number
  maxX: number
  minY: number
  maxY: number
}

interface Sample { t: number; x: number; y: number }

const interactive = 'input, select, textarea, [data-no-pan]'

export class Pan {
  // The view's position on the surface, CSS px: content moves by −(x, y).
  x = 0
  y = 0
  private velocity = { x: 0, y: 0 }
  private press: { id: number; type: string; origin: Sample; samples: Sample[]; dragging: boolean } | null = null
  private dragged = false
  private moved = true
  private bounds: () => Bounds | null

  constructor(bounds: () => Bounds | null = () => null) {
    this.bounds = bounds
  }

  setBounds(bounds: () => Bounds | null) {
    this.bounds = bounds
    this.moved = true
  }

  set(x: number, y: number) {
    this.x = x
    this.y = y
    this.velocity = { x: 0, y: 0 }
    this.clamp()
    this.moved = true
  }

  // Whether the view moved since the last step, after advancing any fling by
  // `dt` ms. Called once per frame, before the frame reads the content.
  step(dt: number) {
    this.fling(dt)
    this.clamp()
    const moved = this.moved
    this.moved = false
    return moved
  }

  attach(element: HTMLElement) {
    const down = (event: PointerEvent) => {
      if (event.pointerType === 'mouse' && event.button !== 0) return
      if ((event.target as Element).closest(interactive)) return
      this.velocity = { x: 0, y: 0 }
      this.dragged = false
      const origin = { t: event.timeStamp, x: event.clientX, y: event.clientY }
      this.press = { id: event.pointerId, type: event.pointerType, origin, samples: [origin], dragging: false }
    }
    const move = (event: PointerEvent) => {
      const press = this.press
      if (event.pointerId !== press?.id) return
      const last = press.samples.at(-1)!
      if (!press.dragging) {
        const slop = press.type === 'mouse' ? DRAG_SLOP.mouse : DRAG_SLOP.touch
        if (Math.hypot(event.clientX - press.origin.x, event.clientY - press.origin.y) < slop) return
        press.dragging = true
        this.dragged = true
        element.setPointerCapture(event.pointerId)
        element.dataset.dragging = ''
      }
      this.x -= event.clientX - last.x
      this.y -= event.clientY - last.y
      this.moved = true
      press.samples.push({ t: event.timeStamp, x: event.clientX, y: event.clientY })
      while (press.samples.length > 2 && event.timeStamp - press.samples[0].t > VELOCITY_WINDOW) press.samples.shift()
    }
    const release = (event: PointerEvent) => {
      const press = this.press
      if (event.pointerId !== press?.id) return
      const first = press.samples[0], last = press.samples.at(-1)!
      const dt = last.t - first.t
      if (press.dragging && event.type === 'pointerup' && dt > 0 && event.timeStamp - last.t < STOPPED_TIME) {
        this.velocity = { x: -(last.x - first.x) / dt, y: -(last.y - first.y) / dt }
      }
      this.press = null
      delete element.dataset.dragging
    }
    // The click that ends a drag is not a click.
    const click = (event: MouseEvent) => {
      if (!this.dragged) return
      event.stopPropagation()
      event.preventDefault()
      this.dragged = false
    }
    const wheel = (event: WheelEvent) => {
      if (event.ctrlKey) return  // pinch-zoom: leave it to the browser
      event.preventDefault()
      const rem = parseFloat(getComputedStyle(document.documentElement).fontSize)
      const unit = event.deltaMode === 1 ? rem : event.deltaMode === 2 ? element.clientHeight : 1
      // A mouse wheel with Shift held pans sideways.
      const [dx, dy] = event.shiftKey && !event.deltaX ? [event.deltaY, 0] : [event.deltaX, event.deltaY]
      this.x += dx * unit
      this.y += dy * unit
      this.velocity = { x: 0, y: 0 }
      this.moved = true
    }
    const key = (event: KeyboardEvent) => {
      if ((event.target as Element).closest(interactive)) return
      const page = element.clientHeight * 0.9
      const steps: Record<string, [number, number]> = {
        ArrowLeft: [-KEY_STEP, 0], ArrowRight: [KEY_STEP, 0], ArrowUp: [0, -KEY_STEP], ArrowDown: [0, KEY_STEP],
        PageUp: [0, -page], PageDown: [0, page],
      }
      const step = steps[event.key]
      if (!step) return
      event.preventDefault()
      this.x += step[0]
      this.y += step[1]
      this.velocity = { x: 0, y: 0 }
      this.moved = true
    }
    element.addEventListener('pointerdown', down)
    element.addEventListener('pointermove', move)
    element.addEventListener('pointerup', release)
    element.addEventListener('pointercancel', release)
    element.addEventListener('click', click, true)
    element.addEventListener('wheel', wheel, { passive: false })
    element.addEventListener('keydown', key)
    return () => {
      element.removeEventListener('pointerdown', down)
      element.removeEventListener('pointermove', move)
      element.removeEventListener('pointerup', release)
      element.removeEventListener('pointercancel', release)
      element.removeEventListener('click', click, true)
      element.removeEventListener('wheel', wheel)
      element.removeEventListener('keydown', key)
    }
  }

  // Advances a fling by `dt` ms, exactly: velocity decays by DECELERATION per
  // ms, so the distance covered is v · (d^dt − 1) / ln d. It stops once all
  // the travel it has left is under half a device pixel.
  private fling(dt: number) {
    if (this.press?.dragging || (!this.velocity.x && !this.velocity.y)) return
    const decay = DECELERATION ** dt
    const travel = (decay - 1) / Math.log(DECELERATION)
    this.x += this.velocity.x * travel
    this.y += this.velocity.y * travel
    this.velocity = { x: this.velocity.x * decay, y: this.velocity.y * decay }
    this.moved = true
    const remaining = Math.hypot(this.velocity.x, this.velocity.y) / -Math.log(DECELERATION)
    if (remaining < 0.5 / (window.devicePixelRatio || 1)) this.velocity = { x: 0, y: 0 }
  }

  // Keeps a bounded view inside its bounds; a fling stops along an edge it
  // reaches.
  private clamp() {
    const bounds = this.bounds()
    if (!bounds) return
    const x = Math.min(Math.max(this.x, bounds.minX), Math.max(bounds.minX, bounds.maxX))
    const y = Math.min(Math.max(this.y, bounds.minY), Math.max(bounds.minY, bounds.maxY))
    if (x !== this.x) { this.velocity.x = 0; this.x = x; this.moved = true }
    if (y !== this.y) { this.velocity.y = 0; this.y = y; this.moved = true }
  }
}
