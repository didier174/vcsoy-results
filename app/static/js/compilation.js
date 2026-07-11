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

let currentParticipantTests = [];
let currentParticipantName = "";

function showParticipantTests(participantId, buttonEl) {
  const el = document.getElementById("participant-tests-" + participantId);
  currentParticipantTests = el ? JSON.parse(el.textContent) : [];
  currentParticipantName = buttonEl.dataset.participantName;

  renderParticipantTests();
  document.getElementById("participant-tests-popup").showModal();
}

function sortParticipantTests(key) {
  const valueFor = (t) => (key === "channel" ? (CHANNEL_LABELS_JS[t.channel] || t.channel) : t[key]);
  currentParticipantTests = [...currentParticipantTests].sort((a, b) => {
    const av = valueFor(a);
    const bv = valueFor(b);
    if (typeof av === "number" && typeof bv === "number") return av - bv;
    return String(av).localeCompare(String(bv), "fr", { numeric: true, sensitivity: "base" });
  });
  renderParticipantTests();
}

function renderParticipantTests() {
  document.getElementById("participant-tests-title").textContent = "Tests — " + currentParticipantName;

  const container = document.getElementById("participant-tests-content");
  container.innerHTML = "";

  if (currentParticipantTests.length === 0) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "Aucun test pris en compte pour ce participant.";
    container.appendChild(empty);
    return;
  }

  const popup = document.getElementById("participant-tests-popup");
  const detailBase = popup.dataset.testDetailBase.replace(/0$/, "");
  const recordUrlFor = (recordId) => popup.dataset.recordDownloadBase.replace("/0/", "/" + recordId + "/");

  const table = document.createElement("table");
  table.className = "participant-tests-table";
  table.innerHTML =
    "<thead><tr>" +
    "<th><button type=\"button\" class=\"table-sort-btn\" data-sort-key=\"test_id\">Test</button></th>" +
    "<th><button type=\"button\" class=\"table-sort-btn\" data-sort-key=\"channel\">Canal</button></th>" +
    "<th><button type=\"button\" class=\"table-sort-btn\" data-sort-key=\"note_brute\">Note brute</button></th>" +
    "<th><button type=\"button\" class=\"table-sort-btn\" data-sort-key=\"note_20\">Note sur 20</button></th>" +
    "<th></th>" +
    "</tr></thead>";
  table.querySelectorAll(".table-sort-btn").forEach((btn) => {
    btn.addEventListener("click", () => sortParticipantTests(btn.dataset.sortKey));
  });

  const tbody = document.createElement("tbody");
  currentParticipantTests.forEach((t) => {
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
