// Active/désactive "Supprimer" (au moins une sélection) selon les cases
// cochées dans le tableau des rapports d'études.
function updateReportActionButtons() {
  const checked = document.querySelectorAll(".report-checkbox:checked").length;
  const deleteBtn = document.getElementById("report-delete-btn");
  if (deleteBtn) deleteBtn.disabled = checked === 0;
}

document.querySelectorAll(".report-checkbox").forEach((cb) => {
  cb.addEventListener("change", updateReportActionButtons);
});
updateReportActionButtons();

// Popup "Créer un rapport d'étude" : le bouton "Créer" ne devient actif
// que lorsqu'un modèle, un participant ET un nom de fichier ont été
// renseignés.
function updateCreateReportSubmit() {
  const templateSel = document.getElementById("create-report-template");
  const participantSel = document.getElementById("create-report-participant");
  const filenameInput = document.getElementById("create-report-filename");
  const submitBtn = document.getElementById("create-report-submit");
  if (!templateSel || !participantSel || !filenameInput || !submitBtn) return;
  submitBtn.disabled = !templateSel.value || !participantSel.value || !filenameInput.value.trim();
}

// Propose un nom de fichier par défaut ("Rapport_Participant_Édition")
// quand le participant est choisi, sans écraser un nom déjà modifié à la
// main par l'utilisateur.
let lastAutoReportFilename = "";

function updateDefaultReportFilename() {
  const participantSel = document.getElementById("create-report-participant");
  const filenameInput = document.getElementById("create-report-filename");
  const popup = document.getElementById("create-report-popup");
  if (!participantSel || !filenameInput || !popup) return;

  const selected = participantSel.options[participantSel.selectedIndex];
  if (!selected || !selected.value) return;

  const participantName = selected.dataset.participantName || selected.textContent.trim();
  const editionLabel = popup.dataset.editionLabel || "";
  const defaultName = `Rapport_${participantName}_${editionLabel}`.replace(/\s+/g, "_");

  if (!filenameInput.value.trim() || filenameInput.value === lastAutoReportFilename) {
    filenameInput.value = defaultName;
  }
  lastAutoReportFilename = defaultName;
  updateCreateReportSubmit();
}

["create-report-template", "create-report-participant", "create-report-filename"].forEach((id) => {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener("input", updateCreateReportSubmit);
  el.addEventListener("change", updateCreateReportSubmit);
});
const createReportParticipantSel = document.getElementById("create-report-participant");
if (createReportParticipantSel) {
  createReportParticipantSel.addEventListener("change", updateDefaultReportFilename);
}
updateCreateReportSubmit();
