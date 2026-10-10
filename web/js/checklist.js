/* Pre-flight step: reads the papers on this laptop, shows every rule with its evidence, gates the throw. */
import { openCamera, closeCamera, scanLoop } from "/js/camera.js";

const $ = (id) => document.getElementById(id);
const STORE_KEY = "vr.checklist.v1";
const STATUS_TAG = { pass: "PASS", fail: "FAIL", warn: "CHECK", manual: "TAP", pending: "WAIT" };
const VERDICT_NOTE = {
  CLEARED: "Every rule passes. Take your throw.",
  REVIEW: "Something needs a second look, but you can still throw.",
  HELD: "Held at the gate. Fix the red items, or try another traveller.",
};

const model = { people: [], inputs: null, ticked: [], result: null, open: new Set(), persona: null, passportBlob: null, stopScan: null };

function loadSaved() {
  try {
    return JSON.parse(localStorage.getItem(STORE_KEY)) || {};
  } catch {
    return {};
  }
}

function save() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify({ persona: model.persona, ticked: model.ticked }));
  } catch {
    /* private window or blocked storage: the checklist still works, it just forgets on refresh */
  }
}

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

function evidence(item) {
  const box = el("div", "evidence");
  box.id = `ev-${item.rule_id}`;
  const rows = [["RULE", item.rule_id], ["KIND", item.source_kind], ["AS OF", item.as_of]];
  const list = el("dl");
  for (const [term, value] of rows) list.append(el("dt", "", term), el("dd", "", value));
  const source = el("dd");
  if (item.source_url) {
    const link = el("a", "", item.source_url.replace(/^https?:\/\//, "").slice(0, 60));
    link.href = item.source_url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    source.append(link);
  } else {
    source.textContent = "No web source. This is a published standard or a scope note.";
  }
  list.append(el("dt", "", "SOURCE"), source);
  list.append(el("dt", "", "TRUST"), el("dd", item.verified ? "ok" : "unverified", item.verified ? "Verified" : "Unverified demo rule. Check the official source."));
  box.append(list);
  if (item.fix) box.append(el("p", "fix", `Fix: ${item.fix}`));
  return box;
}

function renderItem(item) {
  const li = el("li", "cl-item");
  li.dataset.status = item.status;
  li.dataset.rule = item.rule_id;
  const head = el("div", "cl-head");
  head.append(el("span", "tag", STATUS_TAG[item.status] ?? item.status.toUpperCase()));

  const copy = el("div", "cl-copy");
  copy.append(el("p", "cl-label", item.label), el("p", "cl-detail", item.detail));
  head.append(copy);

  if (item.status === "manual" || model.ticked.includes(item.rule_id)) {
    const box = el("input");
    box.type = "checkbox";
    box.checked = item.status === "pass";
    box.setAttribute("aria-label", `I confirm: ${item.label}`);
    box.addEventListener("change", () => toggleManual(item.rule_id, box.checked));
    head.append(box);
  }

  const toggle = el("button", "ghost why", "Why?");
  toggle.type = "button";
  const open = model.open.has(item.rule_id);
  toggle.setAttribute("aria-expanded", String(open));
  toggle.setAttribute("aria-controls", `ev-${item.rule_id}`);
  toggle.addEventListener("click", () => {
    model.open.has(item.rule_id) ? model.open.delete(item.rule_id) : model.open.add(item.rule_id);
    render();
    $("cl-items").querySelector(`[aria-controls="ev-${item.rule_id}"]`)?.focus();
  });
  head.append(toggle);
  li.append(head);

  const drawer = evidence(item);
  drawer.hidden = !open;
  li.append(drawer);
  return li;
}

function renderVerdict(result) {
  const verdict = $("cl-verdict");
  verdict.dataset.verdict = result.verdict;
  const stamp = $("cl-stamp");
  stamp.textContent = result.verdict;
  stamp.classList.remove("thud");
  void stamp.offsetWidth; // restart the landing animation
  stamp.classList.add("thud");
  const percent = Math.round(result.readiness * 100);
  $("cl-ready").textContent = `${percent}`;
  $("cl-fill").style.width = `${percent}%`;
  $("cl-note").textContent = VERDICT_NOTE[result.verdict];
  $("cl-go").disabled = result.verdict === "HELD";
  const bad = result.items.filter((i) => i.status === "fail").length;
  const announce = `${result.verdict}. ${percent} percent ready.${bad ? ` ${bad} item${bad > 1 ? "s" : ""} failed.` : ""}`;
  $("cl-announce").textContent = announce;
}

function render() {
  const { result } = model;
  $("cl-items").replaceChildren(...(result ? result.items.map(renderItem) : []));
  $("cl-empty").hidden = Boolean(result);
  if (result) renderVerdict(result);
}

async function evaluate(api, stale = () => false) {
  const result = await api("/api/checklist", { ...model.inputs, ticked: model.ticked });
  if (stale()) return;
  model.result = result;
  render();
}

async function toggleManual(ruleId, on) {
  model.ticked = on ? [...new Set([...model.ticked, ruleId])] : model.ticked.filter((id) => id !== ruleId);
  save();
  await evaluate(model.api).catch((err) => model.setStatus(err.message, true));
  $("cl-items").querySelector(`li[data-rule="${ruleId}"] input[type="checkbox"]`)?.focus();
}

async function fetchBlob(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error("A sample document could not be loaded.");
  return res.blob();
}

async function readDocuments(passportBlob, boardingBlob) {
  const { api } = model;
  const passport = await api("/api/scan/passport", undefined, { method: "POST", body: passportBlob });
  const boarding = await api("/api/scan/boarding-pass", undefined, { method: "POST", body: boardingBlob });
  return { passport, boarding };
}

async function runWith({ passportBlob, boardingBlob, returnName, hotelName, bag, persona }) {
  const { api, setStatus } = model;
  const run = (model.run = (model.run ?? 0) + 1);
  const stale = () => run !== model.run;
  $("cl-busy").hidden = false;
  setStatus("Reading the papers on this laptop...");
  try {
    const { passport, boarding } = await readDocuments(passportBlob, boardingBlob);
    if (stale()) return;
    model.inputs = {
      mrz_lines: passport.mrz.lines,
      boarding_pass: boarding.raw,
      return_ticket_name: returnName || null,
      hotel_name: hotelName || null,
      bag,
      travel_date: boarding.boarding_pass.flight_date,
    };
    model.persona = persona ?? null;
    if (!persona) model.ticked = [];
    await model.onPassport(passport.mrz.lines);
    await evaluate(api, stale);
    if (stale()) return;
    save();
    setStatus(`Pre-flight verdict: ${model.result.verdict}.`, model.result.verdict === "HELD");
  } catch (err) {
    if (!stale()) setStatus(err.message, true);
  } finally {
    if (!stale()) $("cl-busy").hidden = true;
  }
}

/** Status of one pre-flight rule for the current traveller, or null when nothing has been checked yet. */
export const ruleStatus = (ruleId) => model.result?.items.find((item) => item.rule_id === ruleId)?.status ?? null;

/** Verdict and readiness of the current pre-flight, for the phone card. Null before anything is checked. */
export const preflightSummary = () => (model.result ? { verdict: model.result.verdict, readiness: Math.round(model.result.readiness * 100) } : null);

export async function startSample(person) {
  model.passportBlob = null;
  $("cl-passport-field").hidden = false;
  await useSample(person);
}

async function useSample(person) {
  model.ticked = model.persona === person.key ? model.ticked : [];
  const [passportBlob, boardingBlob] = await Promise.all([fetchBlob(person.images.passport), fetchBlob(person.images.boarding_pass)]);
  $("cl-passport-img").src = person.images.passport;
  $("cl-boarding-img").src = person.images.boarding_pass;
  document.querySelector(".cl-docs").hidden = false;
  await runWith({ passportBlob, boardingBlob, returnName: person.booking_name, hotelName: person.booking_name, bag: person.bag, persona: person.key });
}

function renderPersonas(people) {
  const group = $("cl-people");
  group.replaceChildren(
    ...people.map((person) => {
      const label = el("label", "person");
      const radio = el("input");
      radio.type = "radio";
      radio.name = "person";
      radio.value = person.key;
      radio.checked = person.key === model.persona;
      radio.addEventListener("change", () => startSample(person).catch((err) => model.setStatus(err.message, true)));
      label.append(radio, el("span", "", person.key.charAt(0).toUpperCase() + person.key.slice(1)));
      return label;
    })
  );
}

/** The desk read a passport by camera or upload. Keep it so the boarding pass is the only paper left to show. */
export function acceptPassport(blob) {
  Object.assign(model, { passportBlob: blob, persona: null, result: null, inputs: null, ticked: [] });
  save();
  $("cl-passport-field").hidden = true;
  document.querySelector(".cl-docs").hidden = true;
  $("cl-empty").textContent = "Passport read. Show your boarding pass to the camera, or upload it below.";
  $("cl-own").open = true;
  render();
}

function stopBoardingCamera() {
  model.stopScan?.();
  model.stopScan = null;
  closeCamera($("cl-video"));
  $("cl-finder").hidden = true;
}

async function onBoardingCamera() {
  if (model.stopScan) return stopBoardingCamera();
  if (!model.passportBlob && !$("cl-own-passport").files[0]) {
    model.setStatus("Add the passport photo page first, then show the boarding pass.", true);
    return;
  }
  $("cl-finder").hidden = false;
  try {
    await openCamera($("cl-video"));
  } catch (err) {
    $("cl-finder").hidden = true;
    model.setStatus(err.message, true);
    return;
  }
  $("cl-hint").textContent = "Hold the boarding pass barcode in the frame.";
  model.stopScan = scanLoop($("cl-video"), async (blob) => {
    const boarding = await model.api("/api/scan/boarding-pass", undefined, { method: "POST", body: blob });
    if (!boarding.boarding_pass) return null;
    const bag = $("cl-own-bag").value.split(",").map((x) => x.trim()).filter(Boolean);
    const passportBlob = model.passportBlob || $("cl-own-passport").files[0];
    stopBoardingCamera();
    await runWith({ passportBlob, boardingBlob: blob, returnName: $("cl-own-return").value.trim(), hotelName: $("cl-own-hotel").value.trim(), bag });
    return true;
  }, { onMiss: () => { $("cl-hint").textContent = "Looking for the barcode..."; } });
}

async function onOwnScan(event) {
  event.preventDefault();
  const passportBlob = model.passportBlob || $("cl-own-passport").files[0];
  const boardingBlob = $("cl-own-boarding").files[0];
  if (!passportBlob || !boardingBlob) {
    model.setStatus("Choose a passport photo page and a boarding pass image.", true);
    return;
  }
  const bag = $("cl-own-bag").value.split(",").map((s) => s.trim()).filter(Boolean);
  await runWith({ passportBlob, boardingBlob, returnName: $("cl-own-return").value.trim(), hotelName: $("cl-own-hotel").value.trim(), bag });
}

export async function initChecklist({ api, setStatus, onPassport, onContinue, onBack }) {
  Object.assign(model, { api, setStatus, onPassport });
  const saved = loadSaved();
  model.ticked = Array.isArray(saved.ticked) ? saved.ticked : [];
  model.persona = saved.persona ?? null;
  $("cl-go").addEventListener("click", onContinue);
  $("cl-back").addEventListener("click", onBack);
  $("cl-own-form").addEventListener("submit", onOwnScan);
  $("cl-cam").addEventListener("click", onBoardingCamera);
  try {
    model.people = await api("/api/demo/personas");
    renderPersonas(model.people);
  } catch {
    $("cl-people").replaceChildren(el("p", "help", "Sample travellers are not available. Scan your own papers below."));
  }
  render();
}

/** Called when the step is shown: a refresh keeps the last traveller instead of an empty board. */
export function enterChecklist() {
  if (!$("cl-finder").hidden && !model.stopScan) $("cl-finder").hidden = true;
  if (!model.result && model.persona) {
    const person = model.people?.find((p) => p.key === model.persona);
    if (person) useSample(person).catch((err) => model.setStatus(err.message, true));
  }
}
