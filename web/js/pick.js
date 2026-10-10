const $ = (id) => document.getElementById(id);
const formatDate = (iso) => new Date(iso + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

function card(doc, onPick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "pick-card";
  button.dataset.doc = doc.id;
  const title = document.createElement("p");
  title.className = "label";
  title.textContent = doc.title;
  button.append(title);
  for (const line of doc.lines) {
    const row = document.createElement("p");
    row.className = "pick-line";
    row.textContent = line;
    button.append(row);
  }
  button.addEventListener("click", () => onPick(doc.id));
  return button;
}

function reveal(result, chosen) {
  for (const button of $("pick-cards").children) {
    button.disabled = true;
    if (button.dataset.doc === result.flawed_id) button.dataset.flawed = "true";
    else if (button.dataset.doc === chosen) button.dataset.wrong = "true";
  }
  const headline = document.createElement("p");
  headline.className = "duel-headline";
  headline.textContent = result.correct ? "Turned back. You spotted it." : "That one was fine. Look again:";
  const why = document.createElement("p");
  why.textContent = result.explanation;
  const rule = document.createElement("p");
  rule.className = "help";
  const trust = result.rule.verified ? "" : "Demo rule, unverified. ";
  rule.textContent = `Rule: ${result.rule.label}. ${trust}As of ${formatDate(result.rule.as_of)}. Source: ${result.rule.source_url}`;
  $("pick-out").replaceChildren(headline, why, rule);
}

export function initPick({ api, getContext, setStatus }) {
  let destination = null;
  const choose = async (choice) => {
    try {
      reveal(await api(`/api/pick/${destination}/answer`, { choice }), choice);
    } catch (err) {
      setStatus(err.message, true);
    }
  };
  return {
    async open() {
      const { landing } = getContext();
      if (!landing) return;
      destination = landing.iso3;
      try {
        const deal = await (await fetch(`/api/pick/${destination}`)).json();
        $("pick-cards").replaceChildren(...deal.documents.map((doc) => card(doc, choose)));
        $("pick-out").replaceChildren();
        $("pick").hidden = false;
      } catch (err) {
        setStatus(err.message, true);
      }
    },
    close() {
      $("pick").hidden = true;
    },
  };
}
