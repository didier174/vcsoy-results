/*
 * Popups "Résultats par canal par catégorie" / "Résultats par canal toute
 * catégorie" de la page "Liste des résultats". Les notes par canal de
 * chaque participant sont déjà présentes sur la page (embarquées en JSON),
 * donc aucun aller-retour réseau au clic sur "Afficher".
 */

const CHANNEL_LABELS_JS = {
  phone: "Téléphone",
  mail: "Mail",
  web: "WEB",
  rs: "RS",
  chat: "Chat",
};

function _getPresentationRows() {
  const el = document.getElementById("presentation-data");
  return el ? JSON.parse(el.textContent) : [];
}

function _renderRankingTable(container, entries, showCategory) {
  container.innerHTML = "";

  if (entries.length === 0) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "Aucun résultat pour cette sélection.";
    container.appendChild(empty);
    return;
  }

  const table = document.createElement("table");
  table.className = "participant-tests-table";
  table.innerHTML =
    "<thead><tr><th>Participant</th>" +
    (showCategory ? "<th>Catégorie</th>" : "") +
    "<th>Note sur 20</th></tr></thead>";

  const tbody = document.createElement("tbody");
  entries.forEach((e) => {
    const tr = document.createElement("tr");
    tr.innerHTML =
      "<td>" + e.name + "</td>" +
      (showCategory ? "<td>" + e.category + "</td>" : "") +
      "<td>" + e.note.toFixed(2) + "</td>";
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  container.appendChild(table);
}

function showResultsByCategory() {
  const rows = _getPresentationRows();
  const categoryCode = document.getElementById("results-by-category-select-cat").value;
  const channel = document.getElementById("results-by-category-select-channel").value;

  const entries = rows
    .filter((r) => r.category_code === categoryCode && r.channels[channel].note_20 !== null)
    .map((r) => ({ name: r.participant_name, note: r.channels[channel].note_20 }))
    .sort((a, b) => b.note - a.note);

  _renderRankingTable(document.getElementById("results-by-category-content"), entries, false);
}

function showResultsAllCategories() {
  const rows = _getPresentationRows();
  const channel = document.getElementById("results-all-select-channel").value;

  const entries = rows
    .filter((r) => r.channels[channel].note_20 !== null)
    .map((r) => ({
      name: r.participant_name,
      category: r.category_label + " (" + r.category_code + ")",
      note: r.channels[channel].note_20,
    }))
    .sort((a, b) => b.note - a.note);

  _renderRankingTable(document.getElementById("results-all-categories-content"), entries, true);
}
