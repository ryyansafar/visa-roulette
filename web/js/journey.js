// Airport Experience - static click-through on mock data (step 1 of the build in
// docs/FATHIMA_AIRPORT_EXPERIENCE_PROMPT.md). Scenes 2-7 of the journey; scene 1 (trip card) lives
// in phone.html, which links here. Swapping each scene to the real endpoints is a render-function
// change only - the data shapes already match the backend contract.

import {
  MOCK_PROFILE, MOCK_BOARDING_PASS, MOCK_STAMP, MOCK_PAPERS,
  MOCK_PERSONA, MOCK_INTERVIEW, MOCK_VERDICT_LINE, loadDestination,
} from "./journey_data.js";

const SCENES = ["checkin", "security", "desk", "papers", "gate", "outdoors"];
let index = 0;
let interviewStep = 0;
const placedPapers = new Set();
const heldItems = new Set();

function $(id) { return document.getElementById(id); }

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
  if (name === "desk") renderInterviewTurn();
  if (name === "papers") renderPapers();
  if (name === "gate") renderGate();
  if (name === "outdoors") renderOutdoors();
}

function next() {
  const target = SCENES[Math.min(index + 1, SCENES.length - 1)];
  goTo(target);
}

// --- Scene: boarding-pass check-in ---
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

// --- Scene: security / papers drawer ---
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

// --- Scene: immigration desk ---
function strictnessDots(level) {
  return "●".repeat(level) + "○".repeat(5 - level);
}

function speak(text, done) {
  const caption = $("officer-caption");
  const face = $("officer-face");
  const state = $("desk-state");
  face.classList.add("speaking");
  state.textContent = "Speaking";
  caption.textContent = text;
  // Mock timing only: the real build drives this from actual TTS audio length / boundary events.
  const settle = Math.min(2600, 500 + text.length * 35);
  setTimeout(() => {
    face.classList.remove("speaking");
    state.textContent = done ? "" : "Listening";
  }, settle);
}

function renderInterviewTurn() {
  $("desk-title").textContent = MOCK_PERSONA.title;
  $("desk-strictness").textContent = `How thorough this desk usually is: ${strictnessDots(MOCK_PERSONA.strictness)}`;
  $("visitor-caption").hidden = true;
  $("desk-next").hidden = false;

  if (interviewStep >= MOCK_INTERVIEW.length) {
    speak(MOCK_VERDICT_LINE, true);
    $("desk-next").hidden = true;
    setTimeout(() => goTo("gate"), 1800);
    return;
  }

  const turn = MOCK_INTERVIEW[interviewStep];
  speak(turn.say, false);

  if (turn.stage === "documents_check") {
    $("desk-next").hidden = true;
    setTimeout(() => goTo("papers"), 1200);
  }
}

function advanceInterview(said) {
  if (said) {
    $("visitor-caption").hidden = false;
    $("visitor-caption").textContent = said;
  }
  interviewStep += 1;
  renderInterviewTurn();
}

$("desk-next").addEventListener("click", () => {
  const turn = MOCK_INTERVIEW[interviewStep];
  advanceInterview(turn ? turn.said : null);
});

$("desk-typed-toggle").addEventListener("click", () => {
  $("desk-typed-form").hidden = !$("desk-typed-form").hidden;
});

$("desk-typed-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = $("desk-typed-input");
  advanceInterview(input.value || "(no answer)");
  input.value = "";
  $("desk-typed-form").hidden = true;
});

// --- Scene: papers ---
function renderPapers() {
  const list = $("paper-cards");
  list.replaceChildren();
  for (const paper of MOCK_PAPERS) {
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
  interviewStep += 1; // past documents_check, toward verdict
  goTo("desk");
});

// --- Scene: gate / arrivals ---
function flapRow(text) {
  const row = $("country-flaps");
  row.replaceChildren();
  [...text.toUpperCase()].forEach((ch, i) => {
    const span = document.createElement("span");
    span.className = "flap ticking";
    span.textContent = ch === " " ? " " : ch;
    span.style.animationDelay = `${i * 40}ms`;
    row.append(span);
  });
}

function sourceHost(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return "the official source"; }
}

function renderGate() {
  flapRow(MOCK_PROFILE.destinationName);
  const stamp = $("gate-stamp");
  stamp.textContent = MOCK_STAMP.label;
  stamp.hidden = false;
  stamp.classList.add("thud");
  $("gate-note").textContent = MOCK_STAMP.note;
  $("gate-source").textContent =
    `Source: ${sourceHost(MOCK_STAMP.source_url)}, as of ${MOCK_STAMP.as_of}.` +
    (MOCK_STAMP.verified ? "" : " Demo rules, unverified.");
}
$("gate-continue").addEventListener("click", () => goTo("outdoors"));

// --- Scene: outdoors ---
async function renderOutdoors() {
  const dest = await loadDestination();
  $("outdoors-title").textContent = `Welcome to ${dest.name}`;
  $("outdoors-season").textContent = dest.season;
  $("outdoors-tip").textContent = dest.tip;
  $("outdoors-source").textContent = `Source: ${sourceHost(dest.source)}, as of ${dest.as_of}.`;
  const list = $("outdoors-highlights");
  list.replaceChildren();
  for (const item of dest.highlights) {
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
    interviewStep = MOCK_INTERVIEW.length;
    goTo("gate");
  } else {
    next();
  }
});

renderCheckin();
goTo("checkin");
