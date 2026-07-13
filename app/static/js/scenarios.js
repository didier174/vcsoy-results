// Active "Supprimer" dès qu'au moins un fichier scénario est coché.
function updateScenarioFileActionButtons() {
  const checked = document.querySelectorAll(".scenario-file-checkbox:checked").length;
  const deleteBtn = document.getElementById("scenario-delete-btn");
  if (deleteBtn) deleteBtn.disabled = checked === 0;
}

document.querySelectorAll(".scenario-file-checkbox").forEach((cb) => {
  cb.addEventListener("change", updateScenarioFileActionButtons);
});
updateScenarioFileActionButtons();

// Popup "Créer des fichiers scénarios" : le bouton "Créer" ne devient
// actif que lorsqu'un modèle de Book, un modèle de Problématiques ET un
// participant ont été choisis.
function updateCreateScenarioSubmit() {
  const bookSel = document.getElementById("create-scenario-book");
  const problematiquesSel = document.getElementById("create-scenario-problematiques");
  const participantSel = document.getElementById("create-scenario-participant");
  const submitBtn = document.getElementById("create-scenario-submit");
  if (!bookSel || !problematiquesSel || !participantSel || !submitBtn) return;
  submitBtn.disabled = !bookSel.value || !problematiquesSel.value || !participantSel.value;
}

["create-scenario-book", "create-scenario-problematiques", "create-scenario-participant"].forEach((id) => {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener("change", updateCreateScenarioSubmit);
});
updateCreateScenarioSubmit();
