import { createGlobe } from "/js/globe.js";

const $ = (id) => document.getElementById(id);
const css = (name, fallback) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
const COLORS = {
  home: css("--go", "#4caf7d"), held: css("--go", "#4caf7d"), free: css("--go", "#4caf7d"),
  on_arrival: "hsl(32 90% 56%)", evisa: "hsl(32 90% 56%)", required: css("--held", "#e0553f"),
};
const WORDS = { free: "visa-free", on_arrival: "visa on arrival", evisa: "e-visa", required: "visa needed", held: "visa held", home: "home", unknown: "no rule" };
const POLL_MS = 4000;
const IDLE_MS = 14000;
const SHOW_MS = 7000;

const state = { countries: new Map(), shapes: [], globe: null, total: -1, flashing: false, lastActivity: 0, attract: 0, wall: null };

const phrase = (entry) => {
  const place = state.countries.get(entry.iso3)?.name ?? entry.iso3;
  return `${entry.nickname} (${entry.origin}) → ${place}, ${WORDS[entry.status] ?? entry.label}`;
};

async function loadShapes() {
  const geo = await fetch("/assets/globe/countries.geojson").then((r) => r.json());
  state.shapes = geo.features.map((f) => ({
    iso3: f.properties.ADM0_A3,
    polygons: f.geometry.type === "MultiPolygon" ? f.geometry.coordinates : [f.geometry.coordinates],
  }));
}

function paintPins(pins) {
  const latest = new Map(pins.map((p) => [p.iso3, p.status]));
  state.globe.setOverlay(state.shapes, (iso3) => COLORS[latest.get(iso3)] ?? null);
}

function renderStats({ stats }) {
  const lucky = stats.luckiest_passport;
  $("s-passport").textContent = lucky ? lucky.nationality : "-";
  $("s-passport-note").textContent = lucky
    ? `${Math.round(lucky.rate * 100)}% of its ${lucky.landings} landing${lucky.landings === 1 ? "" : "s"} were visa-free`
    : "Throw a plane to start the race.";
  $("s-total").textContent = String(stats.total);
  $("s-rate").textContent = `${Math.round(stats.visa_free_rate * 100)}%`;
  const top = stats.most_landed;
  $("s-top").textContent = top ? `${state.countries.get(top.iso3)?.name ?? top.iso3} ×${top.count}` : "-";
}

function renderTicker({ ticker }) {
  $("ticker").replaceChildren(...ticker.map((entry) => {
    const li = document.createElement("li");
    li.dataset.status = entry.status;
    const text = document.createElement("span");
    text.textContent = phrase(entry);
    const tag = document.createElement("span");
    tag.className = entry.seeded ? "demo" : "tag";
    tag.textContent = entry.seeded ? "demo" : (WORDS[entry.status] ?? "").toUpperCase();
    li.append(text, tag);
    return li;
  }));
}

async function showLanding(entry, headline) {
  const country = state.countries.get(entry.iso3);
  if (!country || state.flashing || state.globe.isBusy()) return;
  state.flashing = true;
  const flash = $("flash");
  flash.textContent = headline ?? phrase(entry);
  flash.hidden = true;
  await state.globe.land({ lat: country.lat, lon: country.lon }, 9000);
  flash.hidden = false;
  await new Promise((resolve) => setTimeout(resolve, SHOW_MS));
  flash.hidden = true;
  state.globe.resume();
  state.flashing = false;
}

function applyWall(wall) {
  renderStats(wall);
  renderTicker(wall);
  paintPins(wall.pins);
  const fresh = wall.stats.total - state.total;
  if (state.total >= 0 && fresh > 0) {
    const newest = wall.ticker[0];
    state.lastActivity = performance.now();
    if (newest && !newest.seeded) showLanding(newest, `New landing: ${phrase(newest)}`);
  }
  state.total = wall.stats.total;
  state.wall = wall;
}

function attractTick() {
  if (state.flashing || !state.wall?.ticker.length || performance.now() - state.lastActivity < IDLE_MS) return;
  const pool = state.wall.ticker;
  const entry = pool[state.attract++ % pool.length];
  state.lastActivity = performance.now();
  showLanding(entry);
}

async function poll() {
  try {
    const wall = await fetch("/api/wall").then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))));
    applyWall(wall);
    $("status").textContent = "";
  } catch {
    $("status").textContent = "Wall is offline. Retrying.";
  }
}

async function init() {
  try {
    const [countries] = await Promise.all([fetch("/api/countries").then((r) => r.json()), loadShapes()]);
    state.countries = new Map(countries.map((c) => [c.iso3, c]));
    state.globe = await createGlobe($("map"));
  } catch {
    $("status").textContent = "Could not load the globe. Reload the page.";
    return;
  }
  state.lastActivity = performance.now();
  await poll();
  setInterval(poll, POLL_MS);
  setInterval(attractTick, 2000);
}

init();
