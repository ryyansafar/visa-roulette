import { acceptPassport, enterChecklist, initChecklist, preflightSummary, ruleStatus, startSample } from "/js/checklist.js";
import { closeCamera, openCamera, scanLoop, watchThrow } from "/js/camera.js";
import { createGlobe } from "/js/globe.js";
import { createAirMouse } from "/js/airmouse.js";
import { closeDuel, initDuel, openDuel } from "/js/duel.js";
import { initOfficer } from "/js/officer.js";
import { initPick } from "/js/pick.js";
import { buildTrail, easeFlight, flightDurationMs, sampleFlight } from "/js/planeflight.js";
import { createPlane3d, flightScale } from "/js/plane3d.js";
const $ = (id) => document.getElementById(id);
const STEPS = ["profile", "checklist", "throw", "consent", "handoff"];
const W = 1200;
const css = (name, fallback) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
const colors = () => {
  const go = css("--globe-go", css("--go", "#4caf7d"));
  const warn = css("--globe-arrival", css("--warn", "#e8a33a"));
  return { home: go, held: go, free: go, on_arrival: warn, evisa: warn, required: css("--globe-held", css("--held", "#e0553f")) };
};
const KIND_LABEL = { tourist: "Tourist", business: "Business", transit: "Transit", student: "Student", work: "Work", residence: "Residence", evisa: "E-visa" };

const state = { countries: [], shapes: [], profile: null, visaMap: {}, landing: null, throwResult: null, verdict: null, globe: null, busy: false, stopDesk: null, stopThrowCam: null };

async function api(path, body, init = {}) {
  const res = await fetch(path, body === undefined ? init : { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body), ...init });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(describeError(data));
  return data;
}

function describeError(data) {
  const detail = data.detail;
  if (typeof detail === "string") return detail;
  if (detail && detail.message) return detail.message;
  if (Array.isArray(detail) && detail.length) return `Check the form: ${detail[0].loc.slice(1).join(" ")} ${detail[0].msg}`;
  return "Something went wrong. Try again.";
}

function setStatus(text, bad = false) {
  const el = $("status");
  el.textContent = text;
  el.classList.toggle("bad", bad);
}

function show(step) {
  STEPS.forEach((name, i) => {
    $(`step-${name}`).hidden = name !== step;
    const li = document.querySelector(`[data-step="${name}"]`);
    li.toggleAttribute("aria-current", name === step);
    if (name === step) li.setAttribute("aria-current", "step");
    li.dataset.done = String(i < STEPS.indexOf(step));
  });
  if (step !== "profile") stopDesk();
  if (step === "throw") paintGlobe();
  else stopThrowCamera();
  if (step === "throw") syncThrowCamera();
  if (step === "checklist") enterChecklist();
}

function fillCountries(select, selected) {
  select.replaceChildren(...state.countries.map((c) => new Option(c.name, c.iso3, false, c.iso3 === selected)));
}

function addVisaRow(visa = {}) {
  const li = document.createElement("li");
  const country = document.createElement("select");
  fillCountries(country, visa.country || state.countries[0]?.iso3);
  country.setAttribute("aria-label", "Visa country");
  const kind = document.createElement("select");
  Object.entries(KIND_LABEL).forEach(([value, label]) => kind.add(new Option(label, value)));
  kind.value = visa.kind || "tourist";
  kind.setAttribute("aria-label", "Visa type");
  const until = document.createElement("input");
  until.type = "date";
  until.setAttribute("aria-label", "Valid until (optional)");
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "ghost";
  remove.textContent = "Remove";
  remove.addEventListener("click", () => li.remove());
  li.append(country, kind, until, remove);
  $("visa-list").append(li);
}

function readProfile() {
  const visas = [...$("visa-list").children].map((li) => {
    const [country, kind, until] = li.querySelectorAll("select, input");
    return { country: country.value, kind: kind.value, ...(until.value ? { valid_until: until.value } : {}) };
  });
  return {
    origin: $("f-origin").value, nationality: $("f-nationality").value, age: Number($("f-age").value),
    gender: $("f-gender").value, name: $("f-name").value || null, passport_type: $("f-passport").value || null, visas,
  };
}

async function onProfile(event) {
  event.preventDefault();
  $("profile-error").textContent = "";
  try {
    state.profile = await api("/api/profile", readProfile());
    state.visaMap = await api("/api/visa/map", { nationality: state.profile.nationality, visas: state.profile.visas });
    setStatus(`${Object.keys(state.visaMap).length} destinations have a rule on file for this passport.`);
    resetThrow();
    show("checklist");
  } catch (err) {
    $("profile-error").textContent = err.message;
  }
}

function applyPrefill(prefill) {
  if (prefill.nationality) $("f-nationality").value = prefill.nationality;
  if (prefill.age != null) $("f-age").value = prefill.age;
  if (prefill.gender) $("f-gender").value = prefill.gender;
  if (prefill.name) $("f-name").value = prefill.name;
  if (prefill.passport_type) $("f-passport").value = prefill.passport_type;
}

async function fillFromPassport(mrzLines) {
  applyPrefill(await api("/api/profile/prefill", { mrz_lines: mrzLines }));
  state.profile = await api("/api/profile", readProfile());
  state.visaMap = await api("/api/visa/map", { nationality: state.profile.nationality, visas: state.profile.visas });
}

/* ---- immigration desk ---- */
function stopDesk() {
  state.stopDesk?.();
  state.stopDesk = null;
  closeCamera($("desk-video"));
  $("desk-start").textContent = "Start camera";
  $("desk-hint").textContent = "Camera is off.";
  $("desk-video").closest(".viewfinder").dataset.live = "false";
}

async function acceptDeskPassport(blob, scan) {
  stopDesk();
  await fillFromPassport(scan.mrz.lines);
  acceptPassport(blob);
  $("scan-result").textContent = scan.mrz.all_checks_pass ? "Passport read. All check digits pass." : "Passport read, but a check digit failed. The checklist will flag it.";
  setStatus("Passport read on this laptop. Now your boarding pass.");
  show("checklist");
}

async function startDeskCamera() {
  if (state.stopDesk) return stopDesk();
  try {
    await openCamera($("desk-video"));
  } catch (err) {
    $("scan-result").textContent = err.message;
    return;
  }
  $("desk-start").textContent = "Stop camera";
  $("desk-video").closest(".viewfinder").dataset.live = "true";
  $("desk-hint").textContent = "Hold the photo page flat in the frame.";
  $("scan-result").textContent = "";
  state.stopDesk = scanLoop($("desk-video"), async (blob) => {
    const scan = await api("/api/scan/passport", undefined, { method: "POST", body: blob });
    if (!scan.mrz?.all_checks_pass) return null;
    await acceptDeskPassport(blob, scan);
    return true;
  }, { onMiss: () => { $("desk-hint").textContent = "Looking for the two lines at the bottom of the page..."; } });
}

async function onScan(event) {
  const file = event.target.files[0];
  if (!file) return;
  $("scan-result").textContent = "Reading the passport...";
  try {
    await acceptDeskPassport(file, await api("/api/scan/passport", undefined, { method: "POST", body: file }));
  } catch (err) {
    $("scan-result").textContent = err.message;
  }
}

async function pickSample(person, button) {
  document.querySelectorAll("#desk-people button").forEach((b) => (b.disabled = true));
  try {
    await startSample(person);
    show("checklist");
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    document.querySelectorAll("#desk-people button").forEach((b) => (b.disabled = false));
  }
}

async function renderDeskPeople() {
  try {
    const people = await api("/api/demo/personas");
    $("desk-people").replaceChildren(...people.map((person) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "ghost";
      button.textContent = person.key.charAt(0).toUpperCase() + person.key.slice(1);
      button.addEventListener("click", () => pickSample(person, button));
      return button;
    }));
  } catch {
    $("desk-people").textContent = "Sample travellers are not available.";
  }
}

/* ---- globe ---- */
async function loadShapes() {
  const geo = await fetch("/assets/globe/countries.geojson").then((r) => r.json());
  state.shapes = geo.features.map((f) => ({
    iso3: f.properties.ADM0_A3,
    polygons: f.geometry.type === "MultiPolygon" ? f.geometry.coordinates : [f.geometry.coordinates],
  }));
}

function statusOf(iso3) {
  if (!state.profile) return "unknown";
  if (iso3 === state.profile.nationality) return "home";
  return state.visaMap[iso3] || "unknown";
}

function paintGlobe() {
  const palette = colors();
  state.globe?.setOverlay(state.shapes, (iso3) => {
    const status = statusOf(iso3);
    return status === "unknown" ? null : palette[status];
  });
}
window.addEventListener("themechange", () => paintGlobe());

/* ---- throw ---- */
let pickGame = { open() {}, close() {} };
let officer = { open() {}, close() {} };
function resetThrow() {
  state.landing = null;
  state.throwResult = null;
  state.verdict = null;
  state.globe?.resume();
  showPlane(false);
  $("needs").hidden = true;
  $("r-photo").hidden = true;
  closeDuel();
  pickGame.close();
  officer.close();
  $("r-distance").textContent = "---";
  $("r-country").textContent = "-";
  $("r-stamp").hidden = true;
  $("r-note").textContent = "";
  $("keep").disabled = true;
  $("again").disabled = true;
}

const STAMP_TEXT = { free: "VISA-FREE", on_arrival: "ON ARRIVAL", evisa: "E-VISA", required: "VISA NEEDED", held: "VISA HELD", home: "HOME", unknown: "NO RULE" };
const NEED_TAG = { pass: "READY", fail: "FIX", warn: "CHECK", manual: "CONFIRM", pending: "TO DO" };

function renderNeeds(verdict) {
  const { items = [], official_url: official, note } = verdict.needs ?? {};
  const box = $("needs");
  box.hidden = !items.length;
  $("needs-h").textContent = `WHAT YOU NEED FOR ${state.landing?.name?.toUpperCase() ?? "THIS TRIP"}`;
  $("needs-list").replaceChildren(
    ...items.map((item) => {
      const status = item.rule_id ? ruleStatus(item.rule_id) : null;
      const li = document.createElement("li");
      li.dataset.state = status ?? "todo";
      const tag = document.createElement("span");
      tag.className = "need-tag";
      tag.textContent = status ? (NEED_TAG[status] ?? status.toUpperCase()) : "TO DO";
      const label = document.createElement("p");
      label.className = "need-label";
      label.textContent = item.label;
      const detail = document.createElement("p");
      detail.className = "need-detail";
      detail.textContent = item.detail;
      li.append(tag, label, detail);
      return li;
    })
  );
  const foot = $("needs-foot");
  foot.replaceChildren(document.createTextNode(`${(note ?? "").replace(/,?\s*UNVERIFIED demo data\.?/i, ".")} `));
  if (official) {
    const link = document.createElement("a");
    link.href = official;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = official.replace(/^https?:\/\//, "");
    foot.append("Official source: ", link);
  }
}

const planeEl = () => $("plane");
const trailEl = () => $("plane-trail");
let planeRest = "none";
let flight = null; // { raf, done } while a rAF flight is running

function cancelFlight() {
  if (!flight) return;
  cancelAnimationFrame(flight.raf);
  flight.done();
  flight = null;
}

function clearTrail() {
  const trail = trailEl();
  trail.classList.remove("is-fading");
  trail.firstElementChild.setAttribute("points", "");
  trail.toggleAttribute("hidden", true);
}

let plane3d;
let lastPose3d = null;
const getPlane3d = () => {
  if (plane3d === undefined) plane3d = createPlane3d($("map").parentElement);
  return plane3d;
};

const showPlane = (on) => {
  if (!on) {
    cancelFlight();
    clearTrail();
  }
  const p3 = getPlane3d();
  if (p3) p3.show(on);
  else planeEl().toggleAttribute("hidden", !on);
};

// Sub-60 fps tilt is clamped so the cue stays a hint, not a roll: 0.6 of the physical angle, max 35 deg.
const tilt = (deg) => Math.max(-35, Math.min(35, deg * 0.6));

function flyPlane(result) {
  cancelFlight();
  const plane = planeEl();
  const trail = trailEl();
  plane.getAnimations().forEach((a) => a.cancel());
  const heading = result.heading_deg ?? 0;
  const rad = (heading * Math.PI) / 180;
  const box = $("map").getBoundingClientRect();
  const reach = Math.min(box.width, box.height) * 0.7;
  const ahead = { x: Math.sin(rad), y: -Math.cos(rad) };
  const right = { x: Math.cos(rad), y: Math.sin(rad) };
  const range = Math.max(result.range_m || 1, 1);
  const path = result.path?.length > 2 ? result.path : [[0, 0, 0, 1.5], [1, range, 0, 0]];
  const pose = result.pose;
  const lastLateral = path.at(-1)[2];
  // Same screen mapping as before: (forward, lateral) metres -> px offset from the stage centre.
  const project = (s) => {
    const behind = (1 - s.forward / range) * reach;
    const bow = ((s.lateral - lastLateral) / range) * reach;
    return { x: -ahead.x * behind + right.x * bow, y: -ahead.y * behind + right.y * bow };
  };
  const place = (s, p, opacity, u) => {
    const p3 = getPlane3d();
    if (p3) {
      lastPose3d = { x: p.x, y: p.y, yawDeg: heading + s.yawDeg, pitchDeg: s.pitchDeg, bankDeg: s.bankDeg, scale: flightScale(u, s.height), opacity };
      p3.setPose(lastPose3d);
      return;
    }
    const scale = 0.7 + Math.min(s.height, 6) * 0.14;
    plane.style.transform =
      `translate3d(${p.x.toFixed(2)}px, ${p.y.toFixed(2)}px, 0) rotate(${(heading + s.yawDeg).toFixed(2)}deg) ` +
      `perspective(520px) rotateX(${(-tilt(s.pitchDeg)).toFixed(2)}deg) rotateY(${tilt(s.bankDeg).toFixed(2)}deg) scale(${scale.toFixed(3)})`;
    plane.style.opacity = opacity;
  };
  planeRest = `translate3d(0px, 0px, 0) rotate(${heading}deg) scale(0.2)`;
  clearTrail();
  showPlane(true);
  trail.removeAttribute("hidden");
  const line = trail.firstElementChild;
  const trailPts = buildTrail(path, pose, 80).map((s) => project(s));
  const trailStr = trailPts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`);
  const drawTrail = (u, head) => {
    const k = Math.floor(u * (trailStr.length - 1));
    line.setAttribute("points", `${trailStr.slice(0, k + 1).join(" ")} ${head.x.toFixed(1)},${head.y.toFixed(1)}`);
  };
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
    const end = sampleFlight(path, pose, 1);
    const p = project(end);
    place(end, p, 1, 1);
    drawTrail(1, p);
    return Promise.resolve();
  }
  const duration = flightDurationMs(result.flight_s);
  return new Promise((resolve) => {
    const started = performance.now();
    const state = { raf: 0, done: resolve };
    flight = state;
    const frame = (now) => {
      const r = Math.min((now - started) / duration, 1);
      const u = easeFlight(r);
      const s = sampleFlight(path, pose, u);
      const p = project(s);
      place(s, p, Math.min(u / 0.06, 1), u); // fade in over the first ~6% so launch does not pop
      drawTrail(u, p);
      if (r < 1) {
        state.raf = requestAnimationFrame(frame);
      } else {
        flight = null;
        resolve();
      }
    };
    state.raf = requestAnimationFrame(frame);
  });
}

function landPlane3d(p3) {
  if (!p3.isVisible() || !lastPose3d) return;
  trailEl().classList.add("is-fading");
  p3.fadeOut(450, lastPose3d).finally(() => showPlane(false));
}

function landPlane() {
  const p3 = getPlane3d();
  if (p3) return landPlane3d(p3);
  const plane = planeEl();
  if (plane.hasAttribute("hidden")) return;
  trailEl().classList.add("is-fading");
  plane.animate([{ opacity: 1 }, { opacity: 0, transform: planeRest }], { duration: 450, fill: "forwards" }).finished.finally(() => {
    showPlane(false);
    plane.getAnimations().forEach((a) => a.cancel());
  });
}

async function land(result) {
  if (state.busy) return;
  state.busy = true;
  $("keep").disabled = true;
  $("again").disabled = true;
  try {
    state.throwResult = result;
    const landing = await api("/api/landing", { origin: state.profile.origin, heading_deg: result.heading_deg, distance_km: result.distance_km, nationality: state.profile.nationality, visas: state.profile.visas });
    const verdict = await api("/api/visa/requirement", { nationality: state.profile.nationality, destination: landing.iso3, visas: state.profile.visas });
    setStatus("Thrown. The globe is slowing down...");
    flyPlane(result).catch(() => {});
    await state.globe?.land(landing, landing.distance_km);
    landPlane();
    state.landing = landing;
    state.verdict = verdict;
    $("r-distance").textContent = Math.round(landing.distance_km).toLocaleString();
    $("r-country").textContent = landing.name;
    showLandedPhoto(landing);
    const via = verdict.unlocked_by ? ` Unlocked by your ${verdict.unlocked_by} visa.` : "";
    const stamp = $("r-stamp");
    stamp.dataset.status = verdict.status;
    stamp.textContent = STAMP_TEXT[verdict.status] ?? verdict.label.toUpperCase();
    stamp.hidden = false;
    $("r-note").textContent = `${verdict.status === "unknown" ? "" : `${verdict.label}. `}${verdict.note}${via} As of ${new Date(verdict.as_of + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}.`;
    renderNeeds(verdict);
    openDuel(state.profile.nationality);
    pickGame.open();
    officer.open();
    $("keep").disabled = false;
    setStatus(`Landed in ${landing.name}.`);
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    $("again").disabled = false;
    state.busy = false;
  }
}

async function throwWith(path, body) {
  try {
    await land(await api(path, body));
  } catch (err) {
    setStatus(err.message, true);
  }
}

function initFlick() {
  const map = $("map");
  let down = null;
  map.addEventListener("pointerdown", (e) => {
    if (currentMode() === "flick") down = { x: e.clientX, y: e.clientY, t: performance.now() };
  });
  map.addEventListener("pointerup", (e) => {
    if (!down) return;
    const rect = map.getBoundingClientRect();
    const scale = W / rect.width;
    const { x, y, t } = down;
    down = null;
    if (Math.hypot(e.clientX - x, e.clientY - y) * scale < 20) return;
    throwWith("/api/throw/flick", { dx: (e.clientX - x) * scale, dy: (e.clientY - y) * scale, dt_ms: performance.now() - t });
  });
}

function stopThrowCamera() {
  state.stopThrowCam?.();
  state.stopThrowCam = null;
  closeCamera($("throw-video"));
  $("throw-finder").hidden = true;
}

async function syncThrowCamera() {
  stopThrowCamera();
  if (currentMode() !== "camera") return;
  $("throw-finder").hidden = false;
  try {
    await openCamera($("throw-video"));
  } catch (err) {
    $("throw-finder").hidden = true;
    setStatus(err.message, true);
    return;
  }
  $("throw-hint").textContent = "Throw the plane straight at the camera, nose first.";
  state.stopThrowCam = watchThrow($("throw-video"), (track) => throwWith("/api/throw/camera", { track }), {
    onMotion: (moving) => ($("throw-finder").dataset.moving = String(moving)),
  });
}

const currentMode = () => document.querySelector('input[name="mode"]:checked').value;

const MODE_HELP = {
  flick: "Flick the plane across the globe, or throw the board. Double-click for air mouse. Up is north.",
  camera: "Allow the camera, then throw from 2 to 4 metres away.",
  switch: "Press Space to lock the heading, again to lock the power.",
  board: "Hold the board still, then throw.",
};

function initSwitch() {
  let phase = "idle";
  let heading = 0;
  let power = 0;
  let timer = null;
  const sweep = (fn) => {
    const start = performance.now();
    clearInterval(timer);
    timer = setInterval(() => fn(((performance.now() - start) / 1500) % 2), 16);
  };
  const press = () => {
    if (currentMode() !== "switch") return;
    if (phase === "idle") {
      phase = "heading";
      $("meter").hidden = false;
      sweep((p) => { heading = (p % 1) * 359; $("meter-fill").style.width = `${(heading / 359) * 100}%`; });
      setStatus("Heading sweeping. Press to lock.");
    } else if (phase === "heading") {
      phase = "power";
      sweep((p) => { power = p <= 1 ? p : 2 - p; $("meter-fill").style.width = `${power * 100}%`; });
      setStatus(`Heading locked at ${Math.round(heading)} degrees. Press to lock power.`);
    } else {
      clearInterval(timer);
      phase = "idle";
      throwWith("/api/throw/switch", { heading_deg: heading, power });
    }
  };
  $("switch-btn").addEventListener("click", press);
  document.addEventListener("keydown", (e) => {
    if (e.code === "Space" && !$("step-throw").hidden && !["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName)) {
      e.preventDefault();
      press();
    }
  });
  document.querySelectorAll('input[name="mode"]').forEach((radio) =>
    radio.addEventListener("change", () => {
      clearInterval(timer);
      phase = "idle";
      const mode = currentMode();
      $("mode-help").textContent = MODE_HELP[mode];
      $("switch-btn").hidden = mode !== "switch";
      $("meter").hidden = mode !== "switch";
      $("meter-fill").style.width = "0";
      syncThrowCamera();
    })
  );
  $("mode-help").textContent = MODE_HELP.flick;
}

let airMouse = null;

function initAirMouse() {
  const throwReady = () => !$("step-throw").hidden && ["flick", "board"].includes(currentMode());
  airMouse = createAirMouse({
    throwStage: $("map").parentElement,
    setStatus,
    canThrow: throwReady,
    canActivate: () => $("step-throw").hidden || throwReady(),
    onThrow: (flick) => throwWith("/api/throw/flick", flick),
  });
}

async function initBoard() {
  // The hosted (Vercel) deployment has no ESP32 board and no websocket route, so do not open one there.
  const health = await fetch("/api/health").then((r) => r.json()).catch(() => null);
  if (health?.hosted) return;
  const connect = () => {
    const socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/throw`);
    socket.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      airMouse?.handle(msg);
      if (msg.type === "hello" || msg.type === "device") $("device").textContent = (msg.device_online ?? msg.online) ? "ESP32 board connected" : "ESP32 board not connected";
      else if (msg.type === "throw" && !airMouse?.isOn() && !["camera", "switch"].includes(currentMode()) && !$("step-throw").hidden) land(msg);
      else if (msg.type === "rejected") setStatus(msg.message, true);
    };
    socket.onclose = () => setTimeout(connect, 3000);
  };
  connect();
}

/* ---- consent and hand-off ---- */
function enterConsent() {
  const place = state.landing.name;
  $("trip-line").textContent = `${state.profile.origin} to ${place}`;
  $("consent-text").textContent = `I agree to travel to ${place}. ${state.verdict.label}. I understand the visa information is a demo and I will verify it.`;
  $("f-consent").checked = false;
  $("confirm").disabled = true;
  $("consent-error").textContent = "";
  show("consent");
}

async function onConsent(event) {
  event.preventDefault();
  $("consent-error").textContent = "";
  try {
    const result = await api("/api/handoff", {
      profile: state.profile, landing_iso3: state.landing.iso3, lat: state.landing.lat, lon: state.landing.lon,
      budget: Number($("f-budget").value), currency: $("f-currency").value, consent: $("f-consent").checked,
      preflight: preflightSummary(),
      leave: $("f-swap").checked ? { nickname: $("f-nick").value, note: $("f-note").value } : null,
    });
    showStranger(result.stranger);
    drawQr(result.matrix);
    $("phone-url").textContent = result.url;
    show("handoff");
  } catch (err) {
    $("consent-error").textContent = err.message;
  }
}

function showLandedPhoto(landing) {
  const photo = $("r-photo");
  photo.hidden = true;
  photo.onload = () => { photo.hidden = false; };
  photo.alt = `${landing.name}`;
  photo.src = `/assets/places/${landing.iso3}-1.jpg`;
}

function startAirportJourney() {
  const { profile, landing } = state;
  sessionStorage.setItem("vr_journey", JSON.stringify({
    nationality: profile.nationality, destination: landing.iso3, visas: profile.visas || [], name: profile.name || "", needs: [],
  }));
  closeCamera();
  location.href = "/journey.html";
}

const countryName = (iso3) => state.countries?.find((c) => c.iso3 === iso3)?.name || iso3;
const VISA_FOR_YOU = {
  free: "Visa-free for you too.",
  home: "That is your own country.",
  on_arrival: "Visa on arrival for you.",
  evisa: "You would need an e-visa.",
  required: "You would need a visa first.",
  held: "Your visa already covers it.",
  unknown: "Check the rules for your passport.",
};

function showStranger(chip) {
  $("stranger").hidden = !chip;
  if (!chip) return;
  $("chip-route").textContent = `${countryName(chip.origin)} \u2192 ${countryName(chip.landing_iso3)}`;
  $("chip-note").textContent = `\u201c${chip.note}\u201d`;
  $("chip-by").textContent = `${chip.nickname}${chip.seeded ? " (demo traveller)" : ""}`;
  $("chip-visa").textContent = VISA_FOR_YOU[chip.for_you_status] || "";
  $("chip-visa").dataset.tone = chip.for_you_status || "";
}

function drawQr(matrix) {
  const canvas = $("qr");
  const ctx = canvas.getContext("2d");
  const quiet = 4;
  const cell = Math.floor(canvas.width / (matrix.length + quiet * 2));
  const offset = Math.floor((canvas.width - cell * matrix.length) / 2);
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#000";
  matrix.forEach((row, y) => row.forEach((on, x) => on && ctx.fillRect(offset + x * cell, offset + y * cell, cell, cell)));
}

async function init() {
  try {
    state.countries = await api("/api/countries");
    await loadShapes();
  } catch (err) {
    setStatus("Could not reach the booth server. Is it running?", true);
    return;
  }
  fillCountries($("f-origin"), "IND");
  fillCountries($("f-nationality"), "IND");
  $("add-visa").addEventListener("click", () => addVisaRow());
  $("profile-form").addEventListener("submit", onProfile);
  $("scan-file").addEventListener("change", onScan);
  $("desk-start").addEventListener("click", startDeskCamera);
  renderDeskPeople();
  officer = initOfficer({ api, setStatus, getContext: () => ({ profile: state.profile, landing: state.landing }) });
  pickGame = initPick({ api, setStatus, getContext: () => ({ landing: state.landing }) });
  initDuel({ api, setStatus, getContext: () => ({ profile: state.profile, landing: state.landing }) });
  $("again").addEventListener("click", resetThrow);
  $("keep").addEventListener("click", enterConsent);
  $("back-throw").addEventListener("click", () => show("throw"));
  $("f-swap").addEventListener("change", (e) => ($("swap-fields").hidden = !e.target.checked));
  $("f-consent").addEventListener("change", (e) => ($("confirm").disabled = !e.target.checked));
  $("consent-form").addEventListener("submit", onConsent);
  $("restart").addEventListener("click", () => { resetThrow(); show("profile"); });
  $("to-airport").addEventListener("click", startAirportJourney);
  await initChecklist({
    api,
    setStatus,
    onPassport: fillFromPassport,
    onContinue: () => { resetThrow(); show("throw"); setStatus("Throw the plane: flick, camera, switch or board."); },
    onBack: () => show("profile"),
  });
  try {
    state.globe = await createGlobe($("map"));
    paintGlobe();
  } catch {
    const note = document.createElement("p");
    note.className = "hint";
    note.setAttribute("role", "alert");
    note.textContent = "The globe needs WebGL. In Chrome open Settings, System, and turn on hardware acceleration, then reload.";
    $("map").after(note);
    setStatus("The 3D globe needs WebGL.", true);
  }
  initFlick();
  initSwitch();
  initBoard();
  initAirMouse();
  $("meter").hidden = true;
  show("profile");
}

init();
