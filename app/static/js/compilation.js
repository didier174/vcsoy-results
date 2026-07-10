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
    const popup = document.getElementById("participant-tests-popup");
    const detailBase = popup.dataset.testDetailBase.replace(/0$/, "");
    const recordUrlFor = (recordId) => popup.dataset.recordDownloadBase.replace("/0/", "/" + recordId + "/");

    const table = document.createElement("table");
    table.className = "participant-tests-table";
    table.innerHTML =
      "<thead><tr><th>Test</th><th>Canal</th><th>Note brute</th><th>Note sur 20</th><th></th></tr></thead>";
    const tbody = document.createElement("tbody");
    tests.forEach((t) => {
      const tr = document.createElement("tr");
      tr.innerHTML =
        "<td><strong><button type=\"button\" class=\"link-button\">" + t.test_id + "</button></strong></td>" +
        "<td>" + (CHANNEL_LABELS_JS[t.channel] || t.channel) + "</td>" +
        "<td>" + t.note_brute + " / " + t.note_max + "</td>" +
        "<td>" + t.note_20.toFixed(2) + "</td>" +
        "<td>" + (t.record_id ? "<a href=\"" + recordUrlFor(t.record_id) + "\" class=\"btn btn-secondary btn-compact record-link\" target=\"_blank\" rel=\"noopener\">Ouvrir le record</a>" : "") + "</td>";
      tr.querySelector("button").addEventListener("click", () => {
        window.location.href = detailBase + t.id;
      });
      const recordLink = tr.querySelector(".record-link");
      if (recordLink) {
        recordLink.addEventListener("click", (event) => openRecordLink(event, recordLink.href, t.record_is_audio));
      }
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    container.appendChild(table);
  }

  document.getElementById("participant-tests-popup").showModal();
}
