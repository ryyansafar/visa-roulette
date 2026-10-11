// Procedural folded-paper dart rendered with three.js into a transparent canvas laid over the stage.
// Pose input mirrors flyPlane(): screen offset from stage centre (px), yaw/pitch/bank in degrees.
import * as THREE from "/vendor/three.module.min.js";

const BASE_PX = 104;
const VIEW_TILT_DEG = -46;
const VIEW_ROLL_DEG = 24;
const FOV = 38;
const NEAR_SCALE = 3.4;
const FAR_SCALE = 0.3;
const FALLOFF_POW = 1.5;
const DEG = Math.PI / 180;

const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);

/** Perspective falloff: NEAR_SCALE at u=0 (beside the viewer's face) down to FAR_SCALE at u=1, monotone. */
export function flightScale(u, height = 0) {
  const g = (1 - clamp(u, 0, 1)) ** FALLOFF_POW;
  const lift = 0.94 + 0.01 * clamp(height, 0, 6);
  return (FAR_SCALE + (NEAR_SCALE - FAR_SCALE) * g) * lift;
}

const SHADE_INNER = [0.9, 0.9, 0.93];
const SHADE_KEEL = [0.7, 0.73, 0.82];
const SHADE_OUTER = [1, 0.98, 0.94];

function foldedFaces() {
  const nose = [0, 0.5, 0.01];
  const tailTop = [0, -0.5, 0.0];
  const keelBottom = [0, -0.5, -0.17];
  const noseKeel = [0, 0.5, -0.0];
  const side = (s) => {
    const mid = [s * 0.15, -0.5, 0.06];
    const tip = [s * 0.3, -0.5, 0.2];
    return [
      { tri: [nose, tailTop, mid], color: SHADE_INNER },
      { tri: [nose, mid, tip], color: SHADE_OUTER },
    ];
  };
  return [
    ...side(-1),
    ...side(1),
    { tri: [noseKeel, keelBottom, tailTop], color: SHADE_KEEL },
  ];
}

function buildGeometry() {
  const pos = [];
  const col = [];
  foldedFaces().forEach(({ tri, color }) => {
    tri.forEach((v) => {
      pos.push(...v);
      col.push(...color);
    });
  });
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
  geo.computeVertexNormals();
  return geo;
}

function buildCreases() {
  const seg = [0, 0.5, 0.01, 0, -0.5, 0, 0, 0.5, 0.01, -0.15, -0.5, 0.06, 0, 0.5, 0.01, 0.15, -0.5, 0.06, 0, 0.5, 0, 0, -0.5, -0.17];
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(seg, 3));
  return new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: 0x6f7686, transparent: true, opacity: 0.55 }));
}

function buildRig() {
  const geo = buildGeometry();
  const paper = new THREE.MeshStandardMaterial({ vertexColors: true, flatShading: true, roughness: 0.82, metalness: 0, side: THREE.DoubleSide, transparent: true });
  const body = new THREE.Mesh(geo, paper);
  const creases = buildCreases();
  const pivot = new THREE.Group();
  pivot.add(body, creases);
  const root = new THREE.Group();
  root.add(pivot);

  const shadowMat = new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.3, side: THREE.DoubleSide, depthWrite: false });
  const shadow = new THREE.Mesh(geo, shadowMat);
  const shadowRoot = new THREE.Group();
  shadowRoot.add(shadow);
  return { root, pivot, shadowRoot, paper, shadowMat, creases };
}

function buildScene(rig) {
  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a90a4, 2.4));
  const key = new THREE.DirectionalLight(0xfff4e2, 2.6);
  key.position.set(-0.5, -0.4, 1);
  scene.add(key);
  scene.add(rig.shadowRoot, rig.root);
  return scene;
}

export function createPlane3d(stage) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: "high-performance" });
  } catch {
    return null;
  }
  const canvas = renderer.domElement;
  canvas.className = "plane3d";
  canvas.setAttribute("aria-hidden", "true");
  canvas.hidden = true;
  stage.appendChild(canvas);
  renderer.setClearColor(0x000000, 0);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

  const rig = buildRig();
  const scene = buildScene(rig);
  const camera = new THREE.PerspectiveCamera(FOV, 1, 10, 6000);
  let size = { w: 0, h: 0 };
  let fadeRaf = 0;

  const resize = () => {
    const w = stage.clientWidth;
    const h = stage.clientHeight;
    if (!w || !h || (w === size.w && h === size.h)) return;
    size = { w, h };
    renderer.setSize(w, h, false);
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    camera.aspect = w / h;
    camera.position.set(0, 0, h / 2 / Math.tan((FOV / 2) * DEG));
    camera.updateProjectionMatrix();
  };

  const setPose = ({ x, y, yawDeg, pitchDeg, bankDeg, scale, opacity }) => {
    resize();
    const px = BASE_PX * scale;
    const floor = size.h / 2 - px * 0.78;
    const cy = Math.max(-y, -floor);
    rig.root.position.set(x, cy, 0);
    rig.root.rotation.set(0, 0, -yawDeg * DEG);
    rig.root.scale.setScalar(px);
    rig.pivot.rotation.set((VIEW_TILT_DEG + clamp(pitchDeg, -60, 60)) * DEG, (VIEW_ROLL_DEG + clamp(bankDeg, -75, 75)) * DEG, 0, "XYZ");
    const lift = 0.07;
    rig.shadowRoot.position.set(x + px * lift, cy - px * lift, -px * 0.4);
    rig.shadowRoot.rotation.set(0, 0, -yawDeg * DEG);
    rig.shadowRoot.scale.set(px * Math.cos(clamp(bankDeg, -60, 60) * DEG), px * 0.92, 0.001);
    rig.paper.opacity = opacity;
    rig.creases.material.opacity = 0.55 * opacity;
    rig.shadowMat.opacity = 0.3 * opacity;
    renderer.render(scene, camera);
  };

  const stopFade = () => {
    cancelAnimationFrame(fadeRaf);
    fadeRaf = 0;
  };

  const show = (on) => {
    stopFade();
    canvas.hidden = !on;
    if (!on) renderer.clear();
  };

  const fadeOut = (ms, pose) =>
    new Promise((resolve) => {
      stopFade();
      const t0 = performance.now();
      const step = (now) => {
        const k = clamp((now - t0) / ms, 0, 1);
        setPose({ ...pose, scale: pose.scale * (1 - 0.35 * k), opacity: 1 - k });
        if (k < 1) fadeRaf = requestAnimationFrame(step);
        else resolve();
      };
      fadeRaf = requestAnimationFrame(step);
    });

  new ResizeObserver(resize).observe(stage);
  return { setPose, show, fadeOut, isVisible: () => !canvas.hidden };
}
