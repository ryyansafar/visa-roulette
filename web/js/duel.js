const PASSPORTS = ["IND", "GBR", "USA", "ARE"];
const WORDS = { free: "VISA-FREE", on_arrival: "ON ARRIVAL", evisa: "E-VISA", required: "VISA NEEDED", held: "VISA HELD", home: "HOME", unknown: "NO RULE" };
const formatDate = (iso) => new Date(iso + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

const $ = (id) => document.getElementById(id);

function side(entry, stronger) {
  const box = document.createElement("div");
  box.className = "duel-side";
  box.dataset.stronger = String(stronger);
  const code = document.createElement("p");
  code.className = "duel-code";
  code.textContent = entry.nationality;
  const stamp = document.createElement("p");
  stamp.className = "route-stamp";
  stamp.dataset.status = entry.verdict.status;
  stamp.textContent = WORDS[entry.verdict.status] ?? entry.verdict.label.toUpperCase();
  const note = document.createElement("p");
  note.className = "help";
  note.textContent = `${entry.needs.items.length} papers to bring.`;
  box.append(code, stamp, note);
  if (stronger) {
    const badge = document.createElement("p");
    badge.className = "duel-badge";
    badge.textContent = "STRONGER PASSPORT";
    box.append(badge);
  }
  return box;
}

export function renderDuel(result) {
  const out = $("duel-out");
  const footer = document.createElement("p");
  footer.className = "help";
  const { verdict } = result.a;
  footer.textContent = `Demo rules, unverified, as of ${formatDate(verdict.as_of)}. Source: ${verdict.source_url}`;
  const headline = document.createElement("p");
  headline.className = "duel-headline";
  headline.textContent = result.winner ? `${result[result.winner].nationality} wins this landing.` : "A draw. Same entry rules for both.";
  const row = document.createElement("div");
  row.className = "duel-row";
  row.append(side(result.a, result.winner === "a"), side(result.b, result.winner === "b"));
  out.replaceChildren(headline, row, footer);
}

export function initDuel({ api, getContext, setStatus }) {
  const chips = $("duel-chips");
  const pick = async (nationality) => {
    const { profile, landing } = getContext();
    if (!profile || !landing) return;
    try {
      renderDuel(await api("/api/duel", { destination: landing.iso3, a: { nationality: profile.nationality, visas: profile.visas }, b: { nationality } }));
    } catch (err) {
      setStatus(err.message, true);
    }
  };
  chips.replaceChildren(...PASSPORTS.map((code) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ghost";
    button.dataset.passport = code;
    button.textContent = code;
    button.addEventListener("click", () => pick(code));
    return button;
  }));
}

export function openDuel(ownNationality) {
  $("duel").hidden = false;
  $("duel-out").replaceChildren();
  for (const button of $("duel-chips").children) button.hidden = button.dataset.passport === ownNationality;
}

export function closeDuel() {
  $("duel").hidden = true;
}
