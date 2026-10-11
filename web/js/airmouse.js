export const DOUBLE_CLICK_MS = 400;
export const HOLD_MS = 150;
export const TRAIL_MS = 350;
export const MAX_PAUSE_MS = 700;
export const MAX_DT_MS = 150;
export const MIN_SWEEP_PX = 10;
export const CANVAS_W = 1200;
export const HINT = "Air mouse on. Hold the button, sweep, let go to throw. Double-click to leave.";

const CURSOR_SVG = `<svg viewBox="0 0 32 32" width="28" height="28" aria-hidden="true" focusable="false">
  <path d="M3 3 L29 14 L17 17 L14 29 Z" fill="#f4f1e8" stroke="hsl(219 40% 10%)" stroke-width="1.5" stroke-linejoin="round"/>
  <path d="M3 3 L17 17 L14 29 Z" fill="#cfd6e4"/>
</svg>`;

export function createDoubleClick(windowMs = DOUBLE_CLICK_MS) {
  let last = null;
  return {
    hit(now) {
      if (last !== null && now - last <= windowMs) {
        last = null;
        return true;
      }
      last = now;
      return false;
    },
    reset() {
      last = null;
    },
  };
}

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

export function clampPoint(point, size) {
  return { x: clamp(point.x, 0, size.width), y: clamp(point.y, 0, size.height) };
}

export function stepCursor(point, delta, size) {
  return clampPoint({ x: point.x + delta.dx, y: point.y + delta.dy }, size);
}

/**
 * The sweep to throw with: the last bit of cursor travel before the finger lifted, as a canvas-space flick.
 * It looks at the last real movement, not at the moment of release, so pausing a beat before lifting still throws.
 * Returns null when the cursor barely moved while held.
 */
export function flickFromTrail(trail, size, nowMs, canvasW = CANVAS_W, trailMs = TRAIL_MS) {
  if (trail.length < 2) return null;
  const end = trail[trail.length - 1];
  if (nowMs - end.t > MAX_PAUSE_MS) return null;
  const sweep = trail.filter((p) => end.t - p.t <= trailMs);
  const first = sweep[0];
  if (sweep.length < 2 || end.t <= first.t) return null;
  const scale = canvasW / size.width;
  const dx = (end.x - first.x) * scale;
  const dy = (end.y - first.y) * scale;
  if (Math.hypot(dx, dy) < MIN_SWEEP_PX) return null;
  return { dx, dy, dt_ms: Math.min(Math.max(end.t - first.t, 30), MAX_DT_MS) };
}

const CLICKABLE = "button, a, label, input, select, textarea, summary, [role=button], [tabindex]";

/**
 * Air mouse for the whole app. `root` hosts the cursor, `throwStage` is the globe area where a hold-and-sweep throws.
 * Short press = click what is under the cursor, hold + sweep = throw (on the throw step) or scroll (elsewhere),
 * double-press = turn it on or off.
 */
export function createAirMouse({ root = document.body, throwStage, canThrow = () => false, canActivate = () => true, onThrow, setStatus = () => {}, now = () => performance.now() }) {
  const cursor = document.createElement("div");
  cursor.className = "air-cursor";
  cursor.hidden = true;
  cursor.innerHTML = CURSOR_SVG;
  root.append(cursor);

  const clicks = createDoubleClick();
  let active = false;
  let thrown = false;
  let point = { x: 0, y: 0 };
  let trail = [];
  let pressed = false;
  let held = false;
  let holdTimer = null;
  let toggledAt = -Infinity;

  const viewport = () => ({ width: window.innerWidth, height: window.innerHeight });
  const stageSize = () => {
    const rect = throwStage.getBoundingClientRect();
    return { width: rect.width, height: rect.height };
  };
  const inStage = (target) => throwStage.contains(target);

  function place(next) {
    point = clampPoint(next, viewport());
    cursor.style.transform = `translate(${point.x}px, ${point.y}px)`;
    const t = now();
    trail = [...trail.filter((p) => t - p.t <= 1000), { t, x: point.x, y: point.y }];
  }

  function move(dx, dy) {
    const before = point;
    place({ x: point.x + dx, y: point.y + dy });
    if (held && !canThrow()) window.scrollBy(before.x - point.x, before.y - point.y);
  }

  function pulse() {
    cursor.firstElementChild.animate([{ transform: "scale(1)" }, { transform: "scale(0.7)" }, { transform: "scale(1)" }], { duration: 160 });
  }

  function clickAt() {
    const target = document.elementFromPoint(point.x, point.y);
    if (!target) return;
    const control = target.closest(CLICKABLE) ?? target;
    control.focus?.({ preventScroll: true });
    control.click();
  }

  function pressDown() {
    if (pressed) return;
    pressed = true;
    held = false;
    trail = [{ t: now(), x: point.x, y: point.y }];
    clearTimeout(holdTimer);
    holdTimer = setTimeout(() => {
      if (!pressed) return;
      held = true;
      if (active && !thrown) {
        cursor.classList.add("is-held");
        if (canThrow()) setStatus("Holding. Sweep, then let go to throw.");
      }
    }, HOLD_MS);
  }

  function pressUp({ native = false } = {}) {
    if (!pressed) return;
    const wasHeld = held;
    pressed = false;
    held = false;
    clearTimeout(holdTimer);
    cursor.classList.remove("is-held");
    if (wasHeld) return active && canThrow() ? release() : undefined;
    if (clicks.hit(now())) {
      clicks.reset();
      if (active) off();
      else if (canActivate()) on();
      return;
    }
    if (!active || thrown) return;
    pulse();
    if (!native) clickAt();
  }

  function release() {
    if (thrown) return;
    const flick = flickFromTrail(trail, stageSize(), now());
    if (!flick) {
      setStatus("Sweep the cursor while you hold, then let go.");
      return;
    }
    thrown = true;
    cursor.classList.add("is-thrown");
    Promise.resolve(onThrow(flick)).finally(off);
  }

  const onPointerMove = (e) => place({ x: e.clientX, y: e.clientY });

  const onPointerDown = (e) => {
    if (e.button > 0 || !canThrow() || !inStage(e.target)) return;
    e.stopPropagation();
    throwStage.setPointerCapture?.(e.pointerId);
    onPointerMove(e);
    pressDown();
  };

  const onPointerUp = (e) => {
    if (!pressed) return;
    e.stopPropagation();
    pressUp({ native: true });
  };

  const onKey = (e) => {
    if (e.key === "Escape") off();
  };

  /** Feed a /ws/throw message: cursor deltas, board button press and release, tap double-clicks. */
  function handle(msg) {
    if (msg.type === "mouse") {
      if (active && !thrown) move(msg.dx, msg.dy);
    } else if (msg.type === "button") {
      if (msg.down) pressDown();
      else pressUp();
    } else if (msg.type === "double_click") {
      if (!active && canActivate()) on();
    }
  }

  function on() {
    if (active) return;
    active = true;
    thrown = false;
    trail = [];
    toggledAt = now();
    clicks.reset();
    cursor.classList.remove("is-thrown", "is-held");
    cursor.hidden = false;
    const { width, height } = viewport();
    place({ x: width / 2, y: height / 2 });
    document.documentElement.classList.add("airmouse-on");
    setStatus("Air mouse on. Press to click, hold and sweep to throw or scroll, double-press to leave.");
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("pointerup", onPointerUp, true);
    document.addEventListener("keydown", onKey);
  }

  function off() {
    if (!active) return;
    active = false;
    pressed = false;
    held = false;
    toggledAt = now();
    clearTimeout(holdTimer);
    cursor.hidden = true;
    document.documentElement.classList.remove("airmouse-on");
    document.removeEventListener("pointermove", onPointerMove);
    document.removeEventListener("pointerdown", onPointerDown, true);
    document.removeEventListener("pointerup", onPointerUp, true);
    document.removeEventListener("keydown", onKey);
  }

  document.addEventListener("dblclick", () => {
    if (now() - toggledAt < 500) return;
    if (active) off();
    else if (canActivate()) on();
  });

  return { on, off, handle, isOn: () => active };
}
