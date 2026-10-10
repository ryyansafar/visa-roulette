// Pure paper-plane flight sampler (no DOM). Turns the backend's dense
// `path` rows [t_s, forward_m, lateral_m, height_m] (+ optional `pose` rows
// [pitch_deg, bank_deg]) into a smooth, C1-continuous state for any u in [0,1].

/** Real-time playback: physics seconds are multiplied by this (slow motion). 1.5 s flight -> ~2.2 s. */
export const SLOWMO = 1.45;
/** Playback bounds in ms. Long flights cap near 3.2 s, short ones never flash by. */
export const MIN_MS = 1200;
export const MAX_MS = 3200;
/** Final fraction of the playback over which the plane settles, and how much of the speed it sheds. */
export const EASE_TAIL = 0.08;
export const EASE_K = 0.85;

const DEG = 180 / Math.PI;
const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);

export const flightDurationMs = (flightS) => clamp((Number(flightS) || 1) * 1000 * SLOWMO, MIN_MS, MAX_MS);

/**
 * Real-time progress r in [0,1] -> physics progress u in [0,1].
 * NOT an easing: linear (constant slow-motion rate) until the last EASE_TAIL of the
 * playback, then the speed ramps down linearly by EASE_K so the plane settles.
 */
export function easeFlight(r) {
  const x = clamp(r, 0, 1);
  const r0 = 1 - EASE_TAIL;
  const m = 1 / (1 - (EASE_K * EASE_TAIL) / 2);
  if (x <= r0) return m * x;
  const s = (x - r0) / EASE_TAIL;
  return clamp(m * (r0 + EASE_TAIL * (s - (EASE_K * s * s) / 2)), 0, 1);
}

// Fritsch-Carlson / Butland monotone tangents (never overshoot the samples).
function tangents(t, y) {
  const n = t.length;
  const h = new Array(n - 1);
  const d = new Array(n - 1);
  for (let k = 0; k < n - 1; k += 1) {
    h[k] = Math.max(t[k + 1] - t[k], 1e-9);
    d[k] = (y[k + 1] - y[k]) / h[k];
  }
  if (n === 2) return [d[0], d[0]];
  const m = new Array(n);
  for (let k = 1; k < n - 1; k += 1) {
    if (d[k - 1] * d[k] <= 0) {
      m[k] = 0;
    } else {
      const w1 = 2 * h[k] + h[k - 1];
      const w2 = h[k] + 2 * h[k - 1];
      m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k]);
    }
  }
  const edge = (h0, h1, d0, d1) => {
    const e = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1);
    if (Math.sign(e) !== Math.sign(d0)) return 0;
    if (Math.sign(d0) !== Math.sign(d1) && Math.abs(e) > 3 * Math.abs(d0)) return 3 * d0;
    return e;
  };
  m[0] = edge(h[0], h[1], d[0], d[1]);
  m[n - 1] = edge(h[n - 2], h[n - 3] ?? h[n - 2], d[n - 2], d[n - 3] ?? d[n - 2]);
  return m;
}

// Hermite value + derivative on segment k at time tt.
function hermite(t, y, m, k, tt) {
  const h = Math.max(t[k + 1] - t[k], 1e-9);
  const s = clamp((tt - t[k]) / h, 0, 1);
  const s2 = s * s;
  const s3 = s2 * s;
  const value = (2 * s3 - 3 * s2 + 1) * y[k] + (s3 - 2 * s2 + s) * h * m[k] + (-2 * s3 + 3 * s2) * y[k + 1] + (s3 - s2) * h * m[k + 1];
  const slope = ((6 * s2 - 6 * s) * y[k] + (3 * s2 - 4 * s + 1) * h * m[k] + (-6 * s2 + 6 * s) * y[k + 1] + (3 * s2 - 2 * s) * h * m[k + 1]) / h;
  return { value, slope };
}

const cache = new WeakMap();

function prepare(path, pose) {
  const hit = cache.get(path);
  if (hit && hit.pose === pose) return hit;
  const t = path.map((p) => Number(p[0]));
  const f = path.map((p) => Number(p[1]));
  const l = path.map((p) => Number(p[2]));
  const h = path.map((p) => Math.max(Number(p[3]), 0));
  const poseOk = Array.isArray(pose) && pose.length === path.length && pose.every((r) => Array.isArray(r));
  const prepared = {
    pose,
    t, f, l, h,
    mf: tangents(t, f), ml: tangents(t, l), mh: tangents(t, h),
    pitch: poseOk ? pose.map((r) => Number(r[0]) || 0) : null,
    bank: poseOk ? pose.map((r) => Number(r[1]) || 0) : null,
  };
  if (prepared.pitch) {
    prepared.mp = tangents(t, prepared.pitch);
    prepared.mb = tangents(t, prepared.bank);
  }
  cache.set(path, prepared);
  return prepared;
}

function findSegment(t, tt) {
  let lo = 0;
  let hi = t.length - 2;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (t[mid] <= tt) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

/**
 * State at normalised physics time u in [0,1].
 * yawDeg is the ground-track direction relative to the launch/forward axis
 * (positive = turning right), so the nose follows the curve.
 */
export function sampleFlight(path, pose, u) {
  if (!Array.isArray(path) || path.length < 2) return { forward: 0, lateral: 0, height: 0, pitchDeg: 0, bankDeg: 0, yawDeg: 0 };
  const p = prepare(path, pose);
  const t0 = p.t[0];
  const tt = t0 + clamp(u, 0, 1) * (p.t[p.t.length - 1] - t0);
  const k = findSegment(p.t, tt);
  const f = hermite(p.t, p.f, p.mf, k, tt);
  const l = hermite(p.t, p.l, p.ml, k, tt);
  const h = hermite(p.t, p.h, p.mh, k, tt);

  let dF = f.slope;
  let dL = l.slope;
  if (Math.hypot(dF, dL) < 1e-6) {
    dF = p.f[p.f.length - 1] - p.f[0];
    dL = p.l[p.l.length - 1] - p.l[0];
  }
  const yawDeg = Math.atan2(dL, dF) * DEG;

  let pitchDeg;
  let bankDeg = 0;
  if (p.pitch) {
    pitchDeg = hermite(p.t, p.pitch, p.mp, k, tt).value;
    bankDeg = hermite(p.t, p.bank, p.mb, k, tt).value;
  } else {
    pitchDeg = Math.atan2(h.slope, Math.max(Math.hypot(f.slope, l.slope), 1e-9)) * DEG;
  }
  return { forward: f.value, lateral: l.value, height: Math.max(h.value, 0), pitchDeg, bankDeg, yawDeg };
}

/** n+1 evenly spaced (in physics time) samples, for drawing the trail. */
export function buildTrail(path, pose, n = 60) {
  const count = Math.max(Math.floor(n), 1);
  return Array.from({ length: count + 1 }, (_, i) => sampleFlight(path, pose, i / count));
}
