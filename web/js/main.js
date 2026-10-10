import { acceptPassport, enterChecklist, initChecklist, preflightSummary, ruleStatus, startSample } from "/js/checklist.js";
import { closeCamera, openCamera, scanLoop, watchThrow } from "/js/camera.js";
import { createGlobe } from "/js/globe.js";
import { closeDuel, initDuel, openDuel } from "/js/duel.js";
import { initPick } from "/js/pick.js";
const $ = (id) => document.getElementById(id);
const STEPS = ["profile", "checklist", "throw", "consent", "handoff"];
const W = 1200;
const css = (name, fallback) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
const COLORS = {
  home: css("--go", "#4caf7d"), held: css("--go", "#4caf7d"), free: css("--go", "#4caf7d"),
  on_arrival: "hsl(32 90% 56%)", evisa: "hsl(32 90% 56%)", required: css("--held", "#e0553f"),
  unknown: css("--line", "#2b3446"),
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
  state.globe?.setOverlay(state.shapes, (iso3) => {
    const status = statusOf(iso3);
    return status === "unknown" ? null : COLORS[status];
  });
}

/* ---- throw ---- */
let pickGame = { open() {}, close() {} };
function resetThrow() {
  state.landing = null;
  state.throwResult = null;
  state.verdict = null;
  state.globe?.resume();
  showPlane(false);
  $("needs").hidden = true;
  closeDuel();
  pickGame.close();
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
  foot.replaceChildren(document.createTextNode(`${note ?? ""} `));
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
const showPlane = (on) => planeEl().toggleAttribute("hidden", !on);
let planeRest = "none";

function flyPlane(headingDeg) {
  const plane = planeEl();
  const rad = (headingDeg * Math.PI) / 180;
  const box = $("map").getBoundingClientRect();
  const reach = Math.min(box.width, box.height) * 0.7;
  const from = `translate(${-Math.sin(rad) * reach}px, ${Math.cos(rad) * reach}px) rotate(${headingDeg}deg) scale(1.5)`;
  const to = `translate(0px, 0px) rotate(${headingDeg}deg) scale(0.9)`;
  planeRest = `translate(0px, 0px) rotate(${headingDeg}deg) scale(0.2)`;
  showPlane(true);
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
    plane.style.transform = to;
    return Promise.resolve();
  }
  return plane.animate([{ transform: from, opacity: 0 }, { transform: from, opacity: 1, offset: 0.08 }, { transform: to, opacity: 1 }], { duration: 1100, easing: "cubic-bezier(.2,.7,.3,1)", fill: "forwards" }).finished;
}

function landPlane() {
  const plane = planeEl();
  if (plane.hasAttribute("hidden")) return;
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
    flyPlane(result.heading_deg ?? 0).catch(() => {});
    await state.globe?.land(landing, landing.distance_km);
    landPlane();
    state.landing = landing;
    state.verdict = verdict;
    $("r-distance").textContent = Math.round(landing.distance_km).toLocaleString();
    $("r-country").textContent = landing.name;
    const via = verdict.unlocked_by ? ` Unlocked by your ${verdict.unlocked_by} visa.` : "";
    const trust = verdict.verified ? "" : " Unverified demo rule.";
    const stamp = $("r-stamp");
    stamp.dataset.status = verdict.status;
    stamp.textContent = STAMP_TEXT[verdict.status] ?? verdict.label.toUpperCase();
    stamp.hidden = false;
    $("r-note").textContent = `${verdict.status === "unknown" ? "" : `${verdict.label}. `}${verdict.note}${via}${trust} As of ${verdict.as_of}.`;
    renderNeeds(verdict);
    openDuel(state.profile.nationality);
    pickGame.open();
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
  $("throw-hint").textContent = "Throw the plane across the view.";
  state.stopThrowCam = watchThrow($("throw-video"), (flick) => throwWith("/api/throw/flick", flick), {
    mapWidth: W,
    onMotion: (moving) => ($("throw-finder").dataset.moving = String(moving)),
  });
}

const currentMode = () => document.querySelector('input[name="mode"]:checked').value;

const MODE_HELP = {
  flick: "The globe is spinning. Flick the plane across the screen with your mouse or finger. A faster, longer flick throws farther. Up is north.",
  camera: "Allow the camera, then throw the paper plane (or a dart) across its view. A quicker, wider throw lands farther. The globe slows and stops where it would have landed.",
  switch: "Press Space (or the button) once to lock the heading, again to lock the power.",
  board: "Throw the ESP32 board. Hold it still first, then throw.",
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

function initBoard() {
  const connect = () => {
    const socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/throw`);
    socket.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === "hello" || msg.type === "device") $("device").textContent = (msg.device_online ?? msg.online) ? "ESP32 board connected" : "ESP32 board not connected";
      else if (msg.type === "throw" && currentMode() === "board" && !$("step-throw").hidden) land(msg);
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
  pickGame = initPick({ api, setStatus, getContext: () => ({ landing: state.landing }) });
  initDuel({ api, setStatus, getContext: () => ({ profile: state.profile, landing: state.landing }) });
  $("again").addEventListener("click", resetThrow);
  $("keep").addEventListener("click", enterConsent);
  $("back-throw").addEventListener("click", () => show("throw"));
  $("f-swap").addEventListener("change", (e) => ($("swap-fields").hidden = !e.target.checked));
  $("f-consent").addEventListener("change", (e) => ($("confirm").disabled = !e.target.checked));
  $("consent-form").addEventListener("submit", onConsent);
  $("restart").addEventListener("click", () => { resetThrow(); show("profile"); });
  await initChecklist({
    api,
    setStatus,
    onPassport: fillFromPassport,
    onContinue: () => { resetThrow(); show("throw"); setStatus("Throw the plane: flick, camera, switch or board."); },
    onBack: () => show("profile"),
  });
  try {
    state.globe = await createGlobe($("map"));
  } catch {
    setStatus("The 3D globe needs WebGL. Try Chrome or Safari with hardware acceleration on.", true);
  }
  initFlick();
  initSwitch();
  initBoard();
  $("meter").hidden = true;
  show("profile");
}

init();
