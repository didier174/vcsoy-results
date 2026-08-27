/*
 * Page "Caviarder des records" : les boutons Caviarder/Supprimer n'agissent
 * que sur les tests cochés. Aucune donnée n'est chargée en AJAX : le
 * pop-up "Nom(s) à caviarder" contient déjà, pour CHAQUE test de la liste,
 * un bloc de champs (test_result_ids + noms) — JS se contente d'afficher
 * et d'ACTIVER seulement les blocs des tests cochés (les autres restent
 * `disabled`, donc absents de la soumission du formulaire — un champ cadré
 * juste en display:none serait quand même soumis).
 */

function _checkedCaviardageBoxes() {
  return Array.from(document.querySelectorAll(".caviardage-checkbox:checked"));
}

function _updateCaviardageButtons() {
  const checked = _checkedCaviardageBoxes().length;
  const redactBtn = document.getElementById("caviardage-redact-btn");
  const deleteBtn = document.getElementById("caviardage-delete-btn");
  if (redactBtn) redactBtn.disabled = checked === 0;
  if (deleteBtn) deleteBtn.disabled = checked === 0;
}

document.querySelectorAll(".caviardage-checkbox").forEach((cb) => {
  cb.addEventListener("change", _updateCaviardageButtons);
});
_updateCaviardageButtons();

// "Supprimer" : les cases cochées appartiennent déjà au formulaire caché
// #caviardage-actions-form (attribut form="..."), il suffit de le pointer
// vers la bonne action et de le soumettre.
function submitCaviardageDelete() {
  if (_checkedCaviardageBoxes().length === 0) return false;
  if (!confirm("Retirer le(s) test(s) coché(s) de la sélection ? Leur copie caviardée, si elle existe, sera supprimée (jamais le record d'origine).")) {
    return false;
  }
  const form = document.getElementById("caviardage-actions-form");
  form.action = form.dataset.deleteUrl;
  form.submit();
  return false;
}

// "Caviarder" : sépare les tests cochés éligibles (record PDF présent) des
// autres, prévient pour ces derniers, et n'ouvre le pop-up de saisie des
// noms que pour les tests éligibles.
document.addEventListener("DOMContentLoaded", () => {
  const redactBtn = document.getElementById("caviardage-redact-btn");
  if (!redactBtn) return;

  redactBtn.addEventListener("click", () => {
    const checked = _checkedCaviardageBoxes();
    if (checked.length === 0) return;

    const eligible = [];
    const noRecord = [];
    const notPdf = [];
    checked.forEach((cb) => {
      if (cb.dataset.eligible === "true") {
        eligible.push(cb);
      } else if (cb.dataset.hasRecord === "true") {
        notPdf.push(cb.dataset.testNumber);
      } else {
        noRecord.push(cb.dataset.testNumber);
      }
    });

    if (noRecord.length > 0) {
      alert("Impossible de caviarder (aucun record) : " + noRecord.join(", ") + ".");
    }
    if (notPdf.length > 0) {
      alert(
        "Impossible de caviarder (record audio — seuls les PDF sont pris en charge pour l'instant) : "
        + notPdf.join(", ") + "."
      );
    }
    if (eligible.length === 0) return;

    const eligibleIds = new Set(eligible.map((cb) => cb.dataset.testId));
    document.querySelectorAll(".caviardage-name-block").forEach((block) => {
      const testId = block.id.replace("caviardage-name-block-", "");
      const show = eligibleIds.has(testId);
      block.style.display = show ? "" : "none";
      block.disabled = !show;
    });

    document.getElementById("caviardage-names-popup").showModal();
  });
});
