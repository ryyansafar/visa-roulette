import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

// web/ has no package.json "type": module, so load the browser ES module via a data: URL.
const src = readFileSync(new URL("./planeflight.js", import.meta.url), "utf8");
const { buildTrail, easeFlight, flightDurationMs, sampleFlight } = await import(
  `data:text/javascript;base64,${Buffer.from(src).toString("base64")}`
);

const DT = 0.025;
const N = 60; // 1.5 s

// Lofted throw that curves to the right and lands at height 0.
function makePath(curve = 1) {
  const path = [];
  const pose = [];
  for (let i = 0; i <= N; i += 1) {
    const t = i * DT;
    const s = t / (N * DT);
    const forward = 20 * s - 2 * s * s;
    const lateral = curve * 6 * s * s;
    const height = Math.max(0, 4 * Math.sin(Math.PI * s) * (1 - 0.3 * s));
    path.push([t, forward, lateral, height]);
    pose.push([12 * Math.cos(Math.PI * s), curve * 20 * s]);
  }
  return { path, pose };
}

test("hits the sample points exactly", () => {
  const { path, pose } = makePath();
  for (const i of [0, 1, 7, 30, 59, 60]) {
    const s = sampleFlight(path, pose, path[i][0] / path.at(-1)[0]);
    assert.ok(Math.abs(s.forward - path[i][1]) < 1e-9, `forward @${i}`);
    assert.ok(Math.abs(s.lateral - path[i][2]) < 1e-9, `lateral @${i}`);
    assert.ok(Math.abs(s.height - path[i][3]) < 1e-9, `height @${i}`);
    assert.ok(Math.abs(s.pitchDeg - pose[i][0]) < 1e-6, `pitch @${i}`);
    assert.ok(Math.abs(s.bankDeg - pose[i][1]) < 1e-6, `bank @${i}`);
  }
});

test("continuous at 60 fps with no jumps, forward monotone", () => {
  const { path, pose } = makePath();
  const frames = Math.round(flightDurationMs(1.5) / (1000 / 60));
  let prev = sampleFlight(path, pose, easeFlight(0));
  let maxJump = 0;
  for (let i = 1; i <= frames; i += 1) {
    const s = sampleFlight(path, pose, easeFlight(i / frames));
    maxJump = Math.max(maxJump, Math.hypot(s.forward - prev.forward, s.lateral - prev.lateral, s.height - prev.height));
    assert.ok(s.forward >= prev.forward - 1e-9, "forward never goes backwards");
    prev = s;
  }
  assert.ok(maxJump < 20 * 0.03, `max frame jump ${maxJump} too large`);
});

test("never negative height, even when samples touch the ground", () => {
  const path = [[0, 0, 0, 0], [0.025, 1, 0, 0.4], [0.05, 2, 0, 0], [0.075, 3, 0, 0], [0.1, 4, 0, 0]];
  for (let i = 0; i <= 400; i += 1) assert.ok(sampleFlight(path, null, i / 400).height >= 0);
  const noisy = path.map((r, i) => [r[0], r[1], r[2], i === 3 ? -0.2 : r[3]]);
  for (let i = 0; i <= 400; i += 1) assert.ok(sampleFlight(noisy, null, i / 400).height >= 0);
});

test("yaw follows a curving path", () => {
  const { path, pose } = makePath(1);
  const early = sampleFlight(path, pose, 0.05).yawDeg;
  const late = sampleFlight(path, pose, 0.95).yawDeg;
  assert.ok(early > 0 && late > early, `right curve should yaw increasingly right (${early}, ${late})`);
  const left = makePath(-1);
  assert.ok(sampleFlight(left.path, left.pose, 0.9).yawDeg < 0);
  const straight = [[0, 0, 0, 1], [0.5, 5, 0, 1], [1, 10, 0, 1]];
  assert.ok(Math.abs(sampleFlight(straight, null, 0.5).yawDeg) < 1e-6);
});

test("missing or malformed pose falls back to path slope and zero bank", () => {
  const path = [[0, 0, 0, 0], [0.5, 5, 0, 5], [1, 10, 0, 0]];
  const up = sampleFlight(path, undefined, 0.1);
  assert.ok(up.pitchDeg > 20, `climbing pitch ${up.pitchDeg}`);
  assert.equal(up.bankDeg, 0);
  assert.ok(sampleFlight(path, null, 0.95).pitchDeg < 0);
  assert.equal(sampleFlight(path, [[1, 2]], 0.5).bankDeg, 0);
  assert.equal(sampleFlight([], null, 0.5).height, 0);
});

test("easeFlight is real-time proportional then settles", () => {
  assert.equal(easeFlight(0), 0);
  assert.ok(Math.abs(easeFlight(1) - 1) < 1e-12);
  const slope = (a, b) => (easeFlight(b) - easeFlight(a)) / (b - a);
  assert.ok(Math.abs(slope(0.1, 0.5) - slope(0.5, 0.9)) < 1e-9, "constant speed before the tail");
  assert.ok(slope(0.97, 0.99) < slope(0.4, 0.5), "slower at the end");
  let prev = 0;
  for (let i = 1; i <= 200; i += 1) {
    const v = easeFlight(i / 200);
    assert.ok(v >= prev && v <= 1);
    prev = v;
  }
});

test("duration mapping and trail", () => {
  assert.ok(Math.abs(flightDurationMs(1.5) - 2175) < 5);
  assert.equal(flightDurationMs(30), 3200);
  assert.equal(flightDurationMs(0.1), 1200);
  const { path, pose } = makePath();
  const trail = buildTrail(path, pose, 20);
  assert.equal(trail.length, 21);
  assert.ok(Math.abs(trail.at(-1).forward - path.at(-1)[1]) < 1e-9);
});
