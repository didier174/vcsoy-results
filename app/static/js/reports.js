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
