// Airport Experience - scenes 2-7 of the journey (scene 1, the trip card, is phone.html, which
// links here). Check-in and security still use mock data (not yet wired, see
// docs/FATHIMA_AIRPORT_EXPERIENCE_PROMPT.md step 2); the desk, papers, gate and outdoors scenes
// call the real backend, with sessionStorage from phone.html giving the real trip context.

import { MOCK_PROFILE, MOCK_BOARDING_PASS, MOCK_PAPERS } from "./journey_data.js";
import { fetchDestination } from "./officer_api.js";
import * as desk from "./desk.js";

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

// --- Scene: boarding-pass check-in (mock - OCR wiring is a separate step) ---
function renderCheckin() {
  $("checkin-demo").addEventListener("click", () => {
    const pass = MOCK_BOARDING_PASS;
    const fields = $("checkin-fields");
    fields.replaceChildren();
    for (const [label, value] of [["Name", pass.name], ["Flight", pass.flight], ["Route", pass.route], ["Seat", pass.seat]]) {
      const dt = document.createElement("dt"); dt.textContent = label;
      const dd = document.createElement("dd"); dd.textContent = value;
      fields.append(dt, dd);
    }
    fields.hidden = false;
    $("checkin-confirm").hidden = false;
  });
  $("checkin-confirm").addEventListener("click", next);
}

// --- Scene: security / papers drawer (mock list - real needs() wiring is a separate step) ---
function renderSecurity() {
  const list = $("need-list");
  list.replaceChildren();
  for (const paper of MOCK_PAPERS) {
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
  destinationInfo(); // kick off now so it is likely ready by the gate scene
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
  $("outdoors-source").textContent = dest.source ? `Source: ${sourceHost(dest.source)}, as of ${dest.as_of}.` : "";
  const list = $("outdoors-highlights");
  list.replaceChildren();
  for (const item of dest.highlights || []) {
    const li = document.createElement("li");
    const h3 = document.createElement("h3"); h3.textContent = item.title;
    const p = document.createElement("p"); p.textContent = item.blurb;
    li.append(h3, p);
    list.append(li);
  }
}
$("outdoors-done").addEventListener("click", () => {
  window.location.href = "/index.html#souvenir";
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
