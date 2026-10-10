/* Track a plane thrown at the camera: the moving blob's centre and size, frame by frame. Pure maths, no DOM. */

export const TRACK = { w: 160, h: 120, pixelDelta: 34, minShare: 0.0007, maxShare: 0.35, calmMs: 300, maxMs: 1500, minPoints: 4 };

/** Width of the band holding the middle 94% of the changed pixels: the blob's size, ignoring stray noise. */
function extent(hist, total) {
  const tail = total * 0.03;
  let lo = 0;
  let seen = 0;
  while (lo < hist.length && seen + hist[lo] <= tail) seen += hist[lo++];
  let hi = hist.length - 1;
  seen = 0;
  while (hi > lo && seen + hist[hi] <= tail) seen += hist[hi--];
  return Math.max(hi - lo + 1, 1);
}

/**
 * Compare two grey frames. Returns {state, point}: state is "repeat" (same frame twice), "still", "crowd"
 * (too much of the frame moved: a person or a shaking camera) or "moving". The point is mirrored so right = the player's right,
 * with cy in frame-width units (the server's convention) and w the equivalent-square size as a fraction of frame width.
 */
export function measureBlob(gray, previous, cfg = TRACK) {
  const { w, h } = cfg;
  let count = 0;
  let sx = 0;
  let sy = 0;
  let any = 0;
  const cols = new Uint16Array(w);
  const rows = new Uint16Array(h);
  for (let i = 0; i < gray.length; i++) {
    if (gray[i] !== previous[i]) any++;
    if (Math.abs(gray[i] - previous[i]) > cfg.pixelDelta) {
      const x = i % w;
      const y = (i - x) / w;
      count++;
      sx += x;
      sy += y;
      cols[x]++;
      rows[y]++;
    }
  }
  if (any === 0) return { state: "repeat" };
  const share = count / gray.length;
  if (share < cfg.minShare) return { state: "still" };
  if (share > cfg.maxShare) return { state: "crowd" };
  const cx = sx / count;
  const cy = sy / count;
  return { state: "moving", point: { cx: 1 - (cx + 0.5) / w, cy: 0.5 + (cy + 0.5 - h / 2) / w, w: Math.sqrt(extent(cols, count) * extent(rows, count)) / w } };
}

/** Collects points while something moves and hands back the whole track once it has been calm for a moment. */
export function createRecorder(cfg = TRACK) {
  let track = [];
  let lastMoveAt = 0;
  return {
    push(point, now) {
      lastMoveAt = now;
      track.push({ t_ms: now, ...point });
      if (now - track[0].t_ms > cfg.maxMs) track.shift();
    },
    poll(now) {
      if (!track.length || now - lastMoveAt < cfg.calmMs) return null;
      const done = track;
      track = [];
      const t0 = done[0].t_ms;
      return done.length >= cfg.minPoints ? done.map((p) => ({ ...p, t_ms: p.t_ms - t0 })) : null;
    },
  };
}
