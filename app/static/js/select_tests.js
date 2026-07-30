/*
 * Popup "Nouvelle sélection de tests" (page Selection test pour
 * restitution) : filtre le canal proposé selon le participant choisi
 * (attribut data-channels de chaque <option> participant), affiche le bloc
 * de critères du canal choisi quand "Sélection de critères" est actif, et
 * gère la case "Supprimer" du tableau de résultats. Aucune donnée n'est
 * chargée en AJAX : tout est déjà rendu par le serveur, JS ne fait
 * qu'afficher/masquer (même convention que invoice_form.js/tests_list.js).
 */

function _updateChannelOptions() {
  const participantSel = document.getElementById("select-tests-participant");
  const channelSel = document.getElementById("select-tests-channel");
  if (!participantSel || !channelSel) return;

  const selected = participantSel.options[participantSel.selectedIndex];
  const allowed = selected && selected.dataset.channels ? selected.dataset.channels.split(",") : [];

  let firstVisible = null;
  Array.from(channelSel.options).forEach((opt) => {
    const visible = allowed.includes(opt.value);
    opt.hidden = !visible;
    opt.disabled = !visible;
    if (visible && !firstVisible) firstVisible = opt;
  });
  if (channelSel.selectedOptions.length === 0 || channelSel.selectedOptions[0].disabled) {
    if (firstVisible) channelSel.value = firstVisible.value;
  }
  _updateCriteriaBlock();
}

function _updateCriteriaBlock() {
  const channelSel = document.getElementById("select-tests-channel");
  if (!channelSel) return;
  const channel = channelSel.value;
  document.querySelectorAll(".criteria-block").forEach((block) => {
    block.style.display = block.id === "select-tests-criteria-block-" + channel ? "" : "none";
  });
}

function _updateCriteriaMode() {
  const selectionMode = document.getElementById("select-tests-criteria-selection");
  const container = document.getElementById("select-tests-criteria-blocks");
  if (!selectionMode || !container) return;
  container.style.display = selectionMode.checked ? "" : "none";
  if (selectionMode.checked) _updateCriteriaBlock();
}

const participantSel = document.getElementById("select-tests-participant");
const channelSel = document.getElementById("select-tests-channel");
if (participantSel) participantSel.addEventListener("change", _updateChannelOptions);
if (channelSel) channelSel.addEventListener("change", _updateCriteriaBlock);
document.querySelectorAll('input[name="criteria_mode"]').forEach((radio) => {
  radio.addEventListener("change", _updateCriteriaMode);
});
_updateChannelOptions();
_updateCriteriaMode();

// Tableau de résultats : "Supprimer" actif seulement si au moins une case cochée.
function _updateDeleteSelectedTestsButton() {
  const checked = document.querySelectorAll(".selected-test-checkbox:checked").length;
  const btn = document.getElementById("delete-selected-tests-btn");
  if (btn) btn.disabled = checked === 0;
}
document.querySelectorAll(".selected-test-checkbox").forEach((cb) => {
  cb.addEventListener("change", _updateDeleteSelectedTestsButton);
});
_updateDeleteSelectedTestsButton();

// Popup "Détail du test" : mêmes données que celles déjà embarquées en JSON
// par ligne (voir tests_list.js), réunies dans une seule vue au lieu de 2
// popups séparées (code / autres données).
function showSelectedTestDetail(testId) {
  const el = document.getElementById("selected-test-data-" + testId);
  if (!el) return;
  const data = JSON.parse(el.textContent);

  document.getElementById("selected-test-detail-title").textContent =
    "Test " + data.test_id + " — " + data.channel_label;

  const codesContainer = document.getElementById("selected-test-detail-codes");
  codesContainer.innerHTML = "";
  (data.codes || []).forEach((code) => {
    const row = document.createElement("div");
    row.className = "other-data-row";
    const keyEl = document.createElement("span");
    keyEl.className = "other-data-key";
    keyEl.textContent = "Code " + code.number;
    const valueEl = document.createElement("span");
    valueEl.className = "other-data-value";
    const value = (code.value === null || code.value === "") ? "—" : code.value;
    const obs = (code.observation === null || code.observation === "") ? "" : " (" + code.observation + ")";
    valueEl.textContent = value + obs;
    row.appendChild(keyEl);
    row.appendChild(valueEl);
    codesContainer.appendChild(row);
  });

  const otherContainer = document.getElementById("selected-test-detail-other");
  otherContainer.innerHTML = "";
  const entries = Object.entries(data.other_fields || {});
  if (entries.length === 0) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "Aucune autre donnée pour ce test.";
    otherContainer.appendChild(empty);
  } else {
    entries.forEach(([key, value]) => {
      const row = document.createElement("div");
      row.className = "other-data-row";
      const keyEl = document.createElement("span");
      keyEl.className = "other-data-key";
      keyEl.textContent = key;
      const valueEl = document.createElement("span");
      valueEl.className = "other-data-value";
      valueEl.textContent = (value === null || value === "") ? "—" : value;
      row.appendChild(keyEl);
      row.appendChild(valueEl);
      otherContainer.appendChild(row);
    });
  }

  document.getElementById("selected-test-detail-popup").showModal();
}
