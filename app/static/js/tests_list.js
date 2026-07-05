/*
 * Popups de la page "Listes des tests" :
 * - valeur + observation d'un Code N (données déjà présentes sur la page,
 *   embarquées en JSON par test, donc pas d'aller-retour réseau)
 * - "Autres données" d'un test
 * Utilise l'élément natif <dialog> (showModal/close), pris en charge par
 * tous les navigateurs modernes, sans dépendance externe.
 */

function _getTestData(testId) {
  const el = document.getElementById("test-data-" + testId);
  return el ? JSON.parse(el.textContent) : null;
}

function showCodePopup(testId, codeNumber) {
  const data = _getTestData(testId);
  if (!data) return;
  const code = data.codes.find((c) => c.number === codeNumber);
  if (!code) return;

  document.getElementById("code-popup-title").textContent = "Code " + codeNumber;
  document.getElementById("code-popup-value").textContent =
    (code.value === null || code.value === "") ? "(vide)" : code.value;
  document.getElementById("code-popup-obs").textContent =
    (code.observation === null || code.observation === "") ? "(aucune observation)" : code.observation;

  document.getElementById("code-popup").showModal();
}

function showOtherDataPopup(testId) {
  const data = _getTestData(testId);
  if (!data) return;

  const container = document.getElementById("other-data-content");
  container.innerHTML = "";

  const entries = Object.entries(data.other_fields || {});
  if (entries.length === 0) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "Aucune autre donnée pour ce test.";
    container.appendChild(empty);
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
      container.appendChild(row);
    });
  }

  document.getElementById("other-data-popup").showModal();
}
