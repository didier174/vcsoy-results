// Active/désactive "Modifier" (une seule sélection) et "Supprimer" (au
// moins une sélection) selon les cases cochées dans le tableau des
// rapports d'études.
function updateReportActionButtons() {
  const checked = document.querySelectorAll(".report-checkbox:checked").length;
  const modifyBtn = document.getElementById("report-modify-btn");
  const deleteBtn = document.getElementById("report-delete-btn");
  if (modifyBtn) modifyBtn.disabled = checked !== 1;
  if (deleteBtn) deleteBtn.disabled = checked === 0;
}

document.querySelectorAll(".report-checkbox").forEach((cb) => {
  cb.addEventListener("change", updateReportActionButtons);
});
updateReportActionButtons();

// Popup "Créer un rapport d'études" : le bouton "Créer" ne devient actif
// que lorsqu'un modèle ET un participant ont été choisis.
function updateCreateReportSubmit() {
  const templateSel = document.getElementById("create-report-template");
  const participantSel = document.getElementById("create-report-participant");
  const submitBtn = document.getElementById("create-report-submit");
  if (!templateSel || !participantSel || !submitBtn) return;
  submitBtn.disabled = !templateSel.value || !participantSel.value;
}

["create-report-template", "create-report-participant"].forEach((id) => {
  const el = document.getElementById(id);
  if (el) el.addEventListener("change", updateCreateReportSubmit);
});
updateCreateReportSubmit();
