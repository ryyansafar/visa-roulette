/* Spinning 3D globe. It spins fast until a throw, then slows and stops with the landing point facing you. */
import * as THREE from "/vendor/three.module.min.js";

const IDLE_SPIN = 5.2; // rad/s, about one turn a second
const TILT_IDLE = 0.32;
const TEX_W = 4096;
const TEX_H = 2048;

const toRad = (deg) => (deg * Math.PI) / 180;
const easeOutCubic = (t) => 1 - (1 - t) ** 3;
const token = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const normalizer = document.createElement("canvas").getContext("2d");
/** Canvas parses any CSS colour (including space-separated hsl) and reads it back as #rrggbb, which three.js accepts. */
const hex = (css) => { normalizer.fillStyle = "#000"; normalizer.fillStyle = css; return normalizer.fillStyle; };
const palette = () => ({ ocean: token("--globe-ocean"), land: token("--globe-land"), grid: token("--globe-grid"), edge: token("--globe-edge"), pin: token("--text") });

/** Yaw that brings longitude `lon` to face the camera, shifted by whole turns. */
const yawFor = (lon) => -Math.PI / 2 - toRad(lon);

/** Flat matte map: ocean, graticule, neutral land, and status fills only where a visa answer exists. */
function paintTexture(canvas, shapes, colorFor, pal) {
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = pal.ocean;
  ctx.fillRect(0, 0, TEX_W, TEX_H);
  const at = (lon, lat) => [((lon + 180) / 360) * TEX_W, ((90 - lat) / 180) * TEX_H];
  ctx.strokeStyle = pal.grid;
  ctx.lineWidth = 1.6;
  ctx.beginPath();
  for (let lon = -180; lon <= 180; lon += 30) { ctx.moveTo(...at(lon, 90)); ctx.lineTo(...at(lon, -90)); }
  for (let lat = -60; lat <= 60; lat += 30) { ctx.moveTo(...at(-180, lat)); ctx.lineTo(...at(180, lat)); }
  ctx.stroke();
  ctx.strokeStyle = pal.ocean;
  ctx.lineWidth = 1.8;
  ctx.lineJoin = "round";
  for (const shape of shapes) {
    ctx.fillStyle = colorFor(shape.iso3) ?? pal.land;
    for (const polygon of shape.polygons) {
      ctx.beginPath();
      for (const ring of polygon) {
        ring.forEach(([lon, lat], i) => (i ? ctx.lineTo(...at(lon, lat)) : ctx.moveTo(...at(lon, lat))));
        ctx.closePath();
      }
      ctx.fill("evenodd");
      ctx.stroke();
    }
  }
}

export async function createGlobe(canvas, { signal = "#f5e642" } = {}) {
  const { width: cssW, height: cssH } = canvas;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setClearColor(0x000000, 0);
  renderer.setPixelRatio(1);
  renderer.setSize(cssW, cssH, false);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, cssW / cssH, 0.1, 50);
  camera.position.z = 4.1;

  const paint = document.createElement("canvas");
  paint.width = TEX_W;
  paint.height = TEX_H;
  const texture = new THREE.CanvasTexture(paint);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());

  const globe = new THREE.Group();
  const earth = new THREE.Mesh(new THREE.SphereGeometry(1, 96, 64), new THREE.MeshBasicMaterial({ map: texture }));
  globe.add(earth);
  const rim = new THREE.Mesh(new THREE.SphereGeometry(1.008, 96, 64), new THREE.MeshBasicMaterial({ color: hex(palette().edge), side: THREE.BackSide }));
  scene.add(globe, rim);

  const pin = new THREE.Group();
  const pinColor = new THREE.Color(signal);
  pin.add(new THREE.Mesh(new THREE.SphereGeometry(0.022, 16, 12), new THREE.MeshBasicMaterial({ color: pinColor })));
  const ring = new THREE.Mesh(new THREE.RingGeometry(0.05, 0.06, 40), new THREE.MeshBasicMaterial({ color: pinColor, side: THREE.DoubleSide, transparent: true }));
  pin.add(ring);
  pin.visible = false;
  globe.add(pin);

  let overlay = null;
  const repaint = () => {
    const pal = palette();
    paintTexture(paint, overlay?.shapes ?? [], overlay?.colorFor ?? (() => null), pal);
    texture.needsUpdate = true;
    rim.material.color.set(hex(pal.edge));
    pinColor.set(hex(pal.pin));
  };
  repaint();
  window.addEventListener("themechange", repaint);

  globe.rotation.order = "XYZ";
  globe.rotation.x = TILT_IDLE;
  let mode = "spin"; // spin | landing | landed
  let landing = null;
  let last = performance.now();

  const place = (lat, lon, lift = 1.004) => {
    const phi = toRad(lat);
    const lam = toRad(lon);
    const point = new THREE.Vector3(Math.cos(phi) * Math.cos(lam), Math.sin(phi), -Math.cos(phi) * Math.sin(lam));
    pin.position.copy(point.clone().multiplyScalar(lift));
    pin.lookAt(point.clone().multiplyScalar(2));
  };

  const step = (now) => {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    if (mode === "spin") {
      globe.rotation.y += IDLE_SPIN * dt;
    } else if (mode === "landing") {
      const t = Math.min(1, (now - landing.start) / landing.duration);
      const k = easeOutCubic(t);
      globe.rotation.y = landing.fromYaw + (landing.toYaw - landing.fromYaw) * k;
      globe.rotation.x = landing.fromTilt + (landing.toTilt - landing.fromTilt) * k;
      if (t >= 1) {
        mode = "landed";
        landing.done();
      }
    }
    if (pin.visible) ring.scale.setScalar(1 + 0.25 * Math.sin(now / 220));
    if (canvas.offsetParent !== null) renderer.render(scene, camera);
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);

  return {
    /** Recolour countries, e.g. by visa status. `colorFor(iso3)` returns a CSS colour or null. */
    setOverlay(shapes, colorFor) {
      overlay = { shapes, colorFor };
      repaint();
    },
    isBusy: () => mode === "landing",
    resume() {
      pin.visible = false;
      globe.rotation.x = TILT_IDLE;
      mode = "spin";
    },
    /** Slow down from full spin and stop with (lat, lon) facing the camera. Returns a promise that resolves once it has stopped. */
    land({ lat, lon }, distanceKm) {
      if (mode === "landing") return Promise.resolve();
      const power = Math.min(1, Math.max(0, distanceKm / 14000));
      const duration = 3200 + 2600 * power;
      // Start at the idle spin speed: easeOutCubic opens at 3 * distance / duration.
      const wanted = (IDLE_SPIN * duration) / 1000 / 3;
      const turn = Math.PI * 2;
      const fromYaw = globe.rotation.y;
      const target = yawFor(lon);
      const steps = Math.ceil((fromYaw + wanted - target) / turn);
      const toYaw = target + steps * turn;
      place(lat, lon);
      pin.visible = false;
      return new Promise((resolve) => {
        landing = {
          start: performance.now(), duration, fromYaw, toYaw,
          fromTilt: globe.rotation.x, toTilt: toRad(lat),
          done: () => { pin.visible = true; resolve(); },
        };
        mode = "landing";
      });
    },
  };
}
