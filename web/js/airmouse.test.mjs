import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

// web/ has no package.json "type": module, so load the browser ES module via a data: URL.
const src = readFileSync(new URL("./airmouse.js", import.meta.url), "utf8");
const { clampPoint, createDoubleClick, flickFromTrail, stepCursor } = await import(
  `data:text/javascript;base64,${Buffer.from(src).toString("base64")}`
);

test("two clicks inside 400 ms are a double click, a slower pair is not", () => {
  const clicks = createDoubleClick(400);
  assert.equal(clicks.hit(1000), false);
  assert.equal(clicks.hit(1399), true);
  assert.equal(clicks.hit(1500), false);
  assert.equal(clicks.hit(1901), false);
});

test("a double click consumes both clicks, so a third starts a new pair", () => {
  const clicks = createDoubleClick(400);
  clicks.hit(0);
  clicks.hit(100);
  assert.equal(clicks.hit(200), false);
});

test("reset forgets the pending click", () => {
  const clicks = createDoubleClick(400);
  clicks.hit(0);
  clicks.reset();
  assert.equal(clicks.hit(100), false);
});

test("cursor deltas accumulate and clamp to the stage", () => {
  const size = { width: 600, height: 360 };
  let p = { x: 300, y: 180 };
  p = stepCursor(p, { dx: 40, dy: -20 }, size);
  p = stepCursor(p, { dx: 10, dy: 5 }, size);
  assert.deepEqual(p, { x: 350, y: 165 });
  assert.deepEqual(stepCursor(p, { dx: 9999, dy: -9999 }, size), { x: 600, y: 0 });
  assert.deepEqual(clampPoint({ x: -5, y: 500 }, size), { x: 0, y: 360 });
});

const size = { width: 600, height: 360 };

test("a sweep up the screen in the last 350 ms is a north flick in canvas units", () => {
  const trail = [{ t: 900, x: 300, y: 300 }, { t: 1000, x: 300, y: 200 }];
  const f = flickFromTrail(trail, size, 1000);
  assert.deepEqual(f, { dx: 0, dy: -200, dt_ms: 100 });
});

test("a sweep to the right is an east flick", () => {
  const f = flickFromTrail([{ t: 0, x: 100, y: 100 }, { t: 100, x: 200, y: 100 }], size, 100);
  assert.equal(f.dx, 200);
  assert.equal(f.dy, 0);
});

test("pausing a beat before lifting still throws, but a long pause does not", () => {
  const trail = [{ t: 0, x: 300, y: 300 }, { t: 100, x: 300, y: 200 }];
  assert.deepEqual(flickFromTrail(trail, size, 600), { dx: 0, dy: -200, dt_ms: 100 });
  assert.equal(flickFromTrail(trail, size, 1000), null);
});

test("a slow sweep is judged on its last 350 ms and its time is capped so it still has some power", () => {
  const trail = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map((i) => ({ t: i * 100, x: 100 + i * 10, y: 300 }));
  const f = flickFromTrail(trail, size, 900);
  assert.equal(f.dt_ms, 150);
  assert.ok(f.dx >= 60 && f.dy === 0);
});

test("a small deliberate sweep of 10 px is enough", () => {
  assert.ok(flickFromTrail([{ t: 0, x: 100, y: 100 }, { t: 80, x: 110, y: 100 }], size, 100));
});

test("each compass direction gives the matching heading (0 north, 90 east, 180 south, 270 west)", () => {
  const heading = ({ dx, dy }) => ((Math.atan2(dx, -dy) * 180) / Math.PI + 360) % 360;
  const sweep = (dx, dy) => flickFromTrail([{ t: 0, x: 400, y: 300 }, { t: 100, x: 400 + dx, y: 300 + dy }], size, 100);
  assert.equal(Math.round(heading(sweep(0, -80))), 0);
  assert.equal(Math.round(heading(sweep(80, 0))), 90);
  assert.equal(Math.round(heading(sweep(0, 80))), 180);
  assert.equal(Math.round(heading(sweep(-80, 0))), 270);
  assert.equal(Math.round(heading(sweep(80, -80))), 45);
});

test("a tiny wobble or a single point is not a throw", () => {
  assert.equal(flickFromTrail([{ t: 0, x: 300, y: 300 }, { t: 50, x: 303, y: 301 }], size, 50), null);
  assert.equal(flickFromTrail([{ t: 0, x: 300, y: 300 }], size, 0), null);
});

test("a very fast sweep still reports at least 30 ms", () => {
  const f = flickFromTrail([{ t: 0, x: 0, y: 0 }, { t: 5, x: 100, y: 0 }], size, 5);
  assert.equal(f.dt_ms, 30);
});
