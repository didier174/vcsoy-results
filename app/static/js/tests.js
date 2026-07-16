// Active "Supprimer" dès qu'au moins un fichier test est coché.
function updateTestFileActionButtons() {
  const checked = document.querySelectorAll(".test-file-checkbox:checked").length;
  const deleteBtn = document.getElementById("test-delete-btn");
  if (deleteBtn) deleteBtn.disabled = checked === 0;
}

document.querySelectorAll(".test-file-checkbox").forEach((cb) => {
  cb.addEventListener("change", updateTestFileActionButtons);
});
updateTestFileActionButtons();

// Popup "Générer fichier test" : le bouton "Générer" ne devient actif que
// lorsqu'un modèle, un participant ET une langue ont été choisis.
function updateCreateTestSubmit() {
  const templateSel = document.getElementById("create-test-template");
  const participantSel = document.getElementById("create-test-participant");
  const languageSel = document.getElementById("create-test-language");
  const submitBtn = document.getElementById("create-test-submit");
  if (!templateSel || !participantSel || !languageSel || !submitBtn) return;
  submitBtn.disabled = !templateSel.value || !participantSel.value || !languageSel.value;
}

["create-test-template", "create-test-participant", "create-test-language"].forEach((id) => {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener("change", updateCreateTestSubmit);
});
updateCreateTestSubmit();
