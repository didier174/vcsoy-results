/*
 * Popup "liste des tests d'un participant" de la page "Compilation des
 * résultats". Les données de chaque participant sont déjà présentes sur
 * la page (embarquées en JSON), donc aucun aller-retour réseau au clic.
 */

const CHANNEL_LABELS_JS = {
  phone: "Téléphone",
  mail: "Mail",
  web: "WEB",
  rs: "RS",
  chat: "Chat",
};

function showParticipantTests(participantId, buttonEl) {
  const el = document.getElementById("participant-tests-" + participantId);
  const tests = el ? JSON.parse(el.textContent) : [];
  const participantName = buttonEl.dataset.participantName;

  document.getElementById("participant-tests-title").textContent = "Tests — " + participantName;

  const container = document.getElementById("participant-tests-content");
  container.innerHTML = "";

  if (tests.length === 0) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "Aucun test pris en compte pour ce participant.";
    container.appendChild(empty);
  } else {
    const table = document.createElement("table");
    table.className = "participant-tests-table";
    table.innerHTML =
      "<thead><tr><th>Test</th><th>Canal</th><th>Note brute</th><th>Note sur 20</th></tr></thead>";
    const tbody = document.createElement("tbody");
    tests.forEach((t) => {
      const tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" + t.test_id + "</td>" +
        "<td>" + (CHANNEL_LABELS_JS[t.channel] || t.channel) + "</td>" +
        "<td>" + t.note_brute + " / " + t.note_max + "</td>" +
        "<td>" + t.note_20.toFixed(2) + "</td>";
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    container.appendChild(table);
  }

  document.getElementById("participant-tests-popup").showModal();
}
