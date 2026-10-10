// Thin wrappers around the real backend endpoints from
// docs/FATHIMA_AIRPORT_EXPERIENCE_PROMPT.md section 4. Every call can fail (backend down, model
// cold, no mic) - callers decide the offline fallback, this module just surfaces a clean error.

export class ApiError extends Error {
  constructor(code, message, status) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function asJson(res) {
  if (res.ok) return res.json();
  const body = await res.json().catch(() => ({}));
  const detail = body.detail || {};
  throw new ApiError(detail.code || "unknown", detail.message || res.statusText, res.status);
}

export function startInterview(nationality, destination, visas) {
  return fetch("/api/officer/start", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ nationality, destination, visas }),
  }).then(asJson);
}

export function sendTurn(sessionId, said) {
  return fetch("/api/officer/turn", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, said }),
  }).then(asJson);
}

export function listen(sessionId, audioBlob) {
  const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
  return fetch(`/api/officer/listen${qs}`, { method: "POST", body: audioBlob }).then(asJson);
}

export async function speak(text, voice) {
  const res = await fetch("/api/officer/speak", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text, voice }),
  });
  if (!res.ok) await asJson(res); // throws with the right ApiError
  return res.blob();
}

export async function fetchDestination(iso3) {
  try {
    const res = await fetch(`/api/destination/${encodeURIComponent(iso3)}`);
    if (res.ok) return res.json();
  } catch {
    // network error - fall through to the offline fixture below
  }
  const fallback = await fetch("/fixtures/destination.sample.json").catch(() => null);
  if (fallback && fallback.ok) return fallback.json();
  return { name: iso3, highlights: [], season: "", tip: "", source: null, as_of: "", curated: false };
}
