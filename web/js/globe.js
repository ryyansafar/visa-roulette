/* Spinning 3D globe. It spins fast until a throw, then slows and stops with the landing point facing you. */
import * as THREE from "/vendor/three.module.min.js";

const IDLE_SPIN = 5.2; // rad/s, about one turn a second
const TILT_IDLE = 0.32;
const BASE_TEXTURE = "/assets/globe/earth-blue-marble.jpg";
const SKY_TEXTURE = "/assets/globe/night-sky.png";
const TEX_W = 4096;
const TEX_H = 2048;

const toRad = (deg) => (deg * Math.PI) / 180;
const easeOutCubic = (t) => 1 - (1 - t) ** 3;
const loadImage = (src) =>
  new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`Could not load ${src}`));
    img.src = src;
  });

/** Yaw that brings longitude `lon` to face the camera, shifted by whole turns. */
const yawFor = (lon) => -Math.PI / 2 - toRad(lon);

function paintTexture(canvas, base, shapes, colorFor) {
  const ctx = canvas.getContext("2d");
  ctx.drawImage(base, 0, 0, TEX_W, TEX_H);
  const at = (lon, lat) => [((lon + 180) / 360) * TEX_W, ((90 - lat) / 180) * TEX_H];
  for (const shape of shapes) {
    const color = colorFor(shape.iso3);
    ctx.fillStyle = color ?? "transparent";
    ctx.globalAlpha = 0.5;
    ctx.strokeStyle = "rgba(255,255,255,0.35)";
    ctx.lineWidth = 1.2;
    for (const polygon of shape.polygons) {
      ctx.beginPath();
      for (const ring of polygon) {
        ring.forEach(([lon, lat], i) => (i ? ctx.lineTo(...at(lon, lat)) : ctx.moveTo(...at(lon, lat))));
        ctx.closePath();
      }
      if (color) ctx.fill("evenodd");
      ctx.globalAlpha = 1;
      ctx.stroke();
      ctx.globalAlpha = 0.5;
    }
  }
  ctx.globalAlpha = 1;
}

function rimMaterial(color) {
  return new THREE.ShaderMaterial({
    transparent: true,
    side: THREE.BackSide,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    uniforms: { glow: { value: new THREE.Color(color) } },
    vertexShader: "varying vec3 n; void main(){ n = normalize(normalMatrix * normal); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
    fragmentShader: "uniform vec3 glow; varying vec3 n; void main(){ float k = pow(0.72 - dot(n, vec3(0.0,0.0,1.0)), 3.0); gl_FragColor = vec4(glow, 1.0) * k; }",
  });
}

export async function createGlobe(canvas, { signal = "#f5e642" } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(canvas.width, canvas.height, false);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, canvas.width / canvas.height, 0.1, 50);
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
  scene.add(globe, new THREE.Mesh(new THREE.SphereGeometry(1.12, 64, 48), rimMaterial("#6aa7ff")));

  const pin = new THREE.Group();
  const pinColor = new THREE.Color(signal);
  pin.add(new THREE.Mesh(new THREE.SphereGeometry(0.022, 16, 12), new THREE.MeshBasicMaterial({ color: pinColor })));
  const ring = new THREE.Mesh(new THREE.RingGeometry(0.05, 0.06, 40), new THREE.MeshBasicMaterial({ color: pinColor, side: THREE.DoubleSide, transparent: true }));
  pin.add(ring);
  pin.visible = false;
  globe.add(pin);

  const [base, sky] = await Promise.all([loadImage(BASE_TEXTURE), loadImage(SKY_TEXTURE)]);
  const skyTexture = new THREE.Texture(sky);
  skyTexture.mapping = THREE.EquirectangularReflectionMapping;
  skyTexture.colorSpace = THREE.SRGBColorSpace;
  skyTexture.needsUpdate = true;
  scene.background = skyTexture;
  paintTexture(paint, base, [], () => null);
  texture.needsUpdate = true;

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
      paintTexture(paint, base, shapes, colorFor);
      texture.needsUpdate = true;
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
