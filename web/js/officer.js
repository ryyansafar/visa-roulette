const $ = (id) => document.getElementById(id);
const CHIPS = ["What do I bring?", "Why this status?", "Anything I might forget?"];
const OPENING = "In one sentence, tell me what this verdict means for me.";
const formatDate = (iso) => new Date(iso + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

function show(reply) {
  const tag = reply.source === "ai" ? `Local AI (${reply.model}), rules-bound` : "Booth rules";
  $("officer-tag").textContent = tag;
  $("officer-text").textContent = reply.text;
  $("officer-foot").textContent = `Unverified demo rules, as of ${formatDate(reply.as_of)}. Source: ${reply.source_url ?? "none on file"}`;
}

export function initOfficer({ api, getContext, setStatus }) {
  let serial = 0;
  const ask = async (question) => {
    const { profile, landing } = getContext();
    if (!profile || !landing || !question.trim()) return;
    const mine = ++serial;
    $("officer-text").textContent = "...";
    try {
      const reply = await api("/api/operator/ask", { question, nationality: profile.nationality, visas: profile.visas, destination: landing.iso3 });
      if (mine === serial) show(reply);
    } catch (err) {
      if (mine === serial) setStatus(err.message, true);
    }
  };
  $("officer-chips").replaceChildren(...CHIPS.map((text) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ghost";
    button.textContent = text;
    button.addEventListener("click", () => ask(text));
    return button;
  }));
  $("officer-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const field = $("officer-q");
    ask(field.value);
    field.value = "";
  });
  return {
    open() {
      $("officer").hidden = false;
      $("officer-tag").textContent = "Immigration Officer";
      $("officer-foot").textContent = "";
      ask(OPENING);
    },
    close() {
      serial += 1;
      $("officer").hidden = true;
    },
  };
}
