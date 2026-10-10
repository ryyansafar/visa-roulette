// The immigration-desk scene: talks to the real /api/officer/* endpoints, drives the 2D face from
// actual TTS audio (mic.playWithLevel), and falls back to typed input or an offline notice so the
// scene never dead-ends. See docs/FATHIMA_AIRPORT_EXPERIENCE_PROMPT.md section 4.

import * as api from "./officer_api.js";
import * as mic from "./mic.js";

function $(id) { return document.getElementById(id); }

let sessionId = null;
let callbacks = { onDocuments() {}, onVerdict() {}, onOffline() {} };
let busy = false;
let holdingMic = false;

function setFace(state) {
  $("desk-state").textContent = state;
}

function setMouthLevel(level) {
  $("officer-face").querySelector(".mouth").style.transform = `scaleY(${0.25 + Math.min(1, level) * 1.5})`;
}

function setBusy(value) {
  busy = value;
  $("desk-talk").disabled = value || !mic.micAvailable();
  $("desk-typed-input").disabled = value;
  $("desk-typed-form").querySelector("button").disabled = value;
}

async function fakePulse(text) {
  const until = performance.now() + Math.min(2600, 500 + text.length * 35);
  return new Promise((resolve) => {
    const step = (now) => {
      if (now >= until) { setMouthLevel(0); return resolve(); }
      setMouthLevel(0.4 + 0.4 * Math.sin(now / 90));
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}

async function speakLine(text, voice) {
  setFace("Speaking");
  try {
    const blob = await api.speak(text, voice);
    await mic.playWithLevel(blob, setMouthLevel);
  } catch {
    await fakePulse(text); // tts_unavailable or no audio support - still looks alive, just not lip-synced
  }
  setMouthLevel(0);
}

function showConcerns(count) {
  const el = $("desk-concerns");
  el.hidden = count === 0;
  el.textContent = `Concerns noted: ${count}`;
}

async function applyResponse(resp, visitorSaid) {
  if (visitorSaid) {
    $("visitor-caption").hidden = false;
    $("visitor-caption").textContent = visitorSaid;
  }
  $("officer-caption").textContent = resp.say;
  showConcerns(resp.concerns || 0);

  await speakLine(resp.say, resp.persona?.voice);

  if (resp.documents) {
    callbacks.onDocuments(resp.documents);
    return;
  }
  if (resp.done) {
    callbacks.onVerdict(resp.stamp || null, resp.concerns || 0);
    return;
  }
  setFace("Listening");
  setBusy(false);
}

async function handleTurn(said) {
  setBusy(true);
  setFace("Thinking");
  try {
    const resp = await api.sendTurn(sessionId, said);
    await applyResponse(resp, said);
  } catch (err) {
    $("officer-caption").textContent = "That didn't go through. Please try again.";
    setFace("Listening");
    setBusy(false);
  }
}

async function handleVoiceTurn(blob) {
  setBusy(true);
  setFace("Thinking");
  try {
    const resp = await api.listen(sessionId, blob);
    await applyResponse(resp, resp.heard);
  } catch (err) {
    $("officer-caption").textContent = err.code === "stt_unavailable"
      ? "Voice isn't available right now - please type instead."
      : "Didn't catch that - please try again or type it.";
    setFace("Listening");
    setBusy(false);
  }
}

function bindOnce() {
  if (bindOnce._done) return;
  bindOnce._done = true;

  $("desk-typed-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = $("desk-typed-input");
    const text = input.value.trim();
    if (!text || busy) return;
    input.value = "";
    handleTurn(text);
  });

  const talk = $("desk-talk");
  const start = async (event) => {
    event.preventDefault();
    if (busy || holdingMic || !mic.micAvailable()) return;
    holdingMic = true;
    talk.textContent = "Release to send";
    try { await mic.startRecording(); } catch { holdingMic = false; talk.textContent = "Hold to talk"; }
  };
  const stop = async () => {
    if (!holdingMic) return;
    holdingMic = false;
    talk.textContent = "Hold to talk";
    const blob = await mic.stopRecording();
    if (blob && blob.size) handleVoiceTurn(blob);
  };
  talk.addEventListener("pointerdown", start);
  talk.addEventListener("pointerup", stop);
  talk.addEventListener("pointerleave", stop);

  $("desk-offline-skip").addEventListener("click", () => callbacks.onOffline());
}

export function submitDocuments() {
  return handleTurn("Here are my documents.");
}

export async function start(context, cb) {
  bindOnce();
  callbacks = cb;
  sessionId = null;
  $("desk-offline").hidden = true;
  $("officer-caption").textContent = "";
  $("visitor-caption").hidden = true;
  $("desk-concerns").hidden = true;
  $("desk-talk").textContent = "Hold to talk";
  if (!mic.micAvailable()) $("desk-talk").hidden = true;
  setBusy(true);
  setFace("Connecting");
  try {
    const resp = await api.startInterview(context.nationality, context.destination, context.visas || []);
    sessionId = resp.session_id;
    $("desk-title").textContent = resp.persona.title;
    $("desk-strictness").textContent =
      `How thorough this desk usually is: ${"●".repeat(resp.persona.strictness)}${"○".repeat(5 - resp.persona.strictness)}`;
    await applyResponse(resp, null);
  } catch {
    $("desk-offline").hidden = false;
    setFace("");
  }
}
