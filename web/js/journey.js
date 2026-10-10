// Airport Experience - scenes 2-7 of the journey (scene 1, the trip card, is phone.html, which
// links here). Check-in reads the boarding pass shown on the phone through the PC camera (/api/scan/boarding-pass; upload and demo pass as fallbacks), security and papers list the real checklist (/api/visa/requirement -> needs), and the
// desk, gate and outdoors scenes call the officer and destination endpoints. sessionStorage from
// phone.html gives the real trip context.

import { MOCK_PROFILE, MOCK_BOARDING_PASS, MOCK_PAPERS } from "./journey_data.js";
import { fetchDestination } from "./officer_api.js";
import * as desk from "./desk.js";
import { cameraAvailable, openCamera, closeCamera, scanLoop } from "./camera.js";

const SCENES = ["checkin", "security", "desk", "papers", "gate", "outdoors"];
let index = 0;
const heldItems = new Set();
const placedPapers = new Set();
let currentPapers = MOCK_PAPERS;
let currentStamp = null;
let currentConcerns = 0;

function $(id) { return document.getElementById(id); }

function context() {
  try {
    const saved = JSON.parse(sessionStorage.getItem("vr_journey") || "null");
    if (saved && saved.nationality && saved.destination) return saved;
  } catch { /* fall through to mock */ }
  return { nationality: MOCK_PROFILE.nationality, destination: MOCK_PROFILE.destination, visas: [] };
}

let neededPromise = null;
function neededPapers() {
  neededPromise ||= (async () => {
    const ctx = context();
    try {
      const reply = await fetch("/api/visa/requirement", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ nationality: ctx.nationality, destination: ctx.destination, visas: ctx.visas || [] }),
      });
      if (!reply.ok) throw new Error("requirement lookup failed");
      const items = (await reply.json()).needs?.items || [];
      if (items.length) return items.map((item) => ({ id: item.id, label: item.label }));
    } catch { /* offline: fall back to the list carried in the trip card, then the demo list */ }
    if (Array.isArray(ctx.needs) && ctx.needs.length) return ctx.needs.map((label, i) => ({ id: `need-${i}`, label }));
    return MOCK_PAPERS;
  })();
  return neededPromise;
}

let destinationInfoPromise = null;
function destinationInfo() {
  destinationInfoPromise ||= fetchDestination(context().destination);
  return destinationInfoPromise;
}

function showScene(name) {
  for (const scene of SCENES) {
    const el = document.getElementById(`scene-${scene}`);
    if (el) el.hidden = scene !== name;
  }
  $("journey-step").textContent = `Step ${SCENES.indexOf(name) + 1} of ${SCENES.length}`;
}

function goTo(name) {
  index = SCENES.indexOf(name);
  if (name !== "checkin") stopCheckinScan();
  showScene(name);
  if (name === "security") renderSecurity();
  if (name === "desk") enterDesk();
  if (name === "papers") renderPapers();
  if (name === "gate") renderGate();
  if (name === "outdoors") renderOutdoors();
}

function next() {
  goTo(SCENES[Math.min(index + 1, SCENES.length - 1)]);
}

// --- Scene: boarding-pass check-in (real scan, demo pass as the fallback) ---
function showPass(pass) {
  const fields = $("checkin-fields");
  fields.replaceChildren();
  for (const [label, value] of [["Name", pass.name], ["Flight", pass.flight], ["Route", pass.route], ["Seat", pass.seat]]) {
    const dt = document.createElement("dt"); dt.textContent = label;
    const dd = document.createElement("dd"); dd.textContent = value;
    fields.append(dt, dd);
  }
  fields.hidden = false;
  $("checkin-confirm").hidden = false;
}

function passFromScan(scanned) {
  const bp = scanned.boarding_pass;
  return {
    name: `${bp.surname}/${bp.given_names}`,
    flight: `${bp.carrier}${bp.flight}`,
    route: `${bp.origin} to ${bp.destination}`,
    seat: bp.seat,
  };
}

function setScanStatus(text, bad = false) {
  $("checkin-status").textContent = text;
  $("checkin-status").dataset.tone = bad ? "bad" : "";
}

let stopScan = null;

function stopCheckinScan() {
  stopScan?.();
  stopScan = null;
  closeCamera($("checkin-video"));
  $("checkin-frame").hidden = true;
}

async function readPass(blob) {
  const reply = await fetch("/api/scan/boarding-pass", { method: "POST", body: blob });
  if (!reply.ok) return null;
  return passFromScan(await reply.json());
}

function acceptPass(pass) {
  stopCheckinScan();
  showPass(pass);
  setScanStatus("Boarding pass read.");
}

async function startCheckinScan() {
  if (!cameraAvailable()) {
    $("checkin-frame").hidden = true;
    setScanStatus("No camera here. Upload a photo of the pass, or use the demo pass.", true);
    return;
  }
  try {
    await openCamera($("checkin-video"));
  } catch (err) {
    $("checkin-frame").hidden = true;
    setScanStatus(`${err.message} Upload a photo, or use the demo pass.`, true);
    return;
  }
  setScanStatus("Looking for a boarding pass barcode...");
  stopScan = scanLoop($("checkin-video"), async (blob) => {
    const pass = await readPass(blob);
    if (pass) acceptPass(pass);
    return pass;
  }, { onMiss: () => setScanStatus("Hold the pass steady, barcode toward the camera. Raise the phone brightness.") });
}

function renderCheckin() {
  $("checkin-file").addEventListener("change", async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    setScanStatus("Reading your boarding pass...");
    try {
      const pass = await readPass(file);
      if (!pass) throw new Error("Could not read that photo.");
      acceptPass(pass);
    } catch (err) {
      setScanStatus(`${err.message} Try again, or use the demo pass.`, true);
    }
  });
  $("checkin-demo").addEventListener("click", () => {
    const name = context().name;
    stopCheckinScan();
    showPass({ ...MOCK_BOARDING_PASS, name: name ? name.toUpperCase() : MOCK_BOARDING_PASS.name });
    setScanStatus("");
  });
  $("checkin-confirm").addEventListener("click", next);
  startCheckinScan();
}

// --- Scene: security / papers drawer (the real checklist for this passport and destination) ---
async function renderSecurity() {
  const list = $("need-list");
  list.replaceChildren();
  for (const paper of await neededPapers()) {
    const li = document.createElement("li");
    li.textContent = paper.label;
    li.dataset.held = "false";
    li.tabIndex = 0;
    li.addEventListener("click", () => {
      const held = !heldItems.has(paper.id);
      held ? heldItems.add(paper.id) : heldItems.delete(paper.id);
      li.dataset.held = String(held);
    });
    list.append(li);
  }
}
$("security-continue").addEventListener("click", () => goTo("desk"));

// --- Scene: immigration desk (real /api/officer/*) ---
function enterDesk() {
  destinationInfo();
  neededPapers(); // kick off now so it is likely ready by the gate scene
  desk.start(context(), {
    onDocuments(papers) {
      currentPapers = papers.length ? papers : MOCK_PAPERS;
      goTo("papers");
    },
    onVerdict(stamp, concerns) {
      currentStamp = stamp;
      currentConcerns = concerns;
      goTo("gate");
    },
    onOffline() {
      currentStamp = null;
      currentConcerns = 0;
      goTo("gate");
    },
  });
}

// --- Scene: papers ---
function renderPapers() {
  const list = $("paper-cards");
  list.replaceChildren();
  for (const paper of currentPapers) {
    const li = document.createElement("li");
    li.textContent = paper.label;
    li.dataset.placed = String(placedPapers.has(paper.id));
    li.tabIndex = 0;
    li.addEventListener("click", () => {
      placedPapers.add(paper.id);
      li.dataset.placed = "true";
    });
    list.append(li);
  }
}
$("papers-continue").addEventListener("click", () => {
  // Show the desk UI again without starting a new session - this continues the one from
  // enterDesk(), it does not call desk.start() again.
  index = SCENES.indexOf("desk");
  showScene("desk");
  desk.submitDocuments();
});

// --- Scene: gate / arrivals ---
function flapRow(text) {
  const row = $("country-flaps");
  row.replaceChildren();
  [...text.toUpperCase()].forEach((ch, i) => {
    const span = document.createElement("span");
    span.className = "flap ticking";
    span.textContent = ch === " " ? " " : ch;
    span.style.animationDelay = `${i * 40}ms`;
    row.append(span);
  });
}

function sourceHost(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return "the official source"; }
}

async function renderGate() {
  const dest = await destinationInfo();
  flapRow(dest.name || context().destination);
  const stampEl = $("gate-stamp");
  if (currentStamp) {
    stampEl.textContent = currentStamp.label;
    stampEl.hidden = false;
    stampEl.classList.add("thud");
    $("gate-note").textContent = currentStamp.note;
    $("gate-source").textContent =
      `Source: ${sourceHost(currentStamp.source_url)}, as of ${currentStamp.as_of}.` +
      (currentStamp.verified ? "" : " Demo rules, unverified.") +
      (currentConcerns ? " Answers can be noted. The stamp comes from the rules." : "");
  } else {
    stampEl.hidden = true;
    $("gate-note").textContent = "The desk could not be reached, so there is no stamp to show this time.";
    $("gate-source").textContent = "";
  }
}
$("gate-continue").addEventListener("click", () => goTo("outdoors"));

// --- Scene: outdoors ---
async function renderOutdoors() {
  const dest = await destinationInfo();
  $("outdoors-title").textContent = `Welcome to ${dest.name}`;
  $("outdoors-season").textContent = dest.season || "";
  $("outdoors-tip").textContent = dest.tip || "";
  $("outdoors-source").textContent = (dest.source ? `Source: ${sourceHost(dest.source)}, as of ${dest.as_of}. ` : "") + "Photos: Wikimedia Commons, credits in assets/places/credits.json.";
  const list = $("outdoors-highlights");
  list.replaceChildren();
  for (const [i, item] of (dest.highlights || []).entries()) {
    const li = document.createElement("li");
    const photo = document.createElement("img");
    photo.className = "place-photo";
    photo.alt = item.title;
    photo.loading = "lazy";
    photo.addEventListener("error", () => photo.remove());
    photo.src = `/assets/places/${dest.iso3}-${i + 1}.jpg`;
    li.append(photo);
    const h3 = document.createElement("h3"); h3.textContent = item.title;
    const p = document.createElement("p"); p.textContent = item.blurb;
    li.append(h3, p);
    list.append(li);
  }
}
$("outdoors-done").addEventListener("click", () => {
  // The souvenir swap happens at the booth; the trip card on the phone shows the stranger's souvenir.
  window.location.href = location.hash.length > 1 ? `/phone.html${location.hash}` : "/";
});

// --- Skip: moves past the current scene without blocking the journey ---
$("journey-skip").addEventListener("click", () => {
  if (SCENES[index] === "desk" || SCENES[index] === "papers") {
    currentStamp = null;
    currentConcerns = 0;
    goTo("gate");
  } else {
    next();
  }
});

renderCheckin();
goTo("checkin");
