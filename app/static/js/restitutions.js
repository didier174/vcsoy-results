// Active/désactive "Supprimer" (au moins une sélection) selon les cases
// cochées dans le tableau des restitutions.
function updateRestitutionActionButtons() {
  const checked = document.querySelectorAll(".restitution-checkbox:checked").length;
  const deleteBtn = document.getElementById("restitution-delete-btn");
  if (deleteBtn) deleteBtn.disabled = checked === 0;
}

document.querySelectorAll(".restitution-checkbox").forEach((cb) => {
  cb.addEventListener("change", updateRestitutionActionButtons);
});
updateRestitutionActionButtons();

// Popup "Créer une restitution" : le bouton "Créer" ne devient actif que
// lorsqu'un modèle, un participant ET un nom de fichier ont été renseignés.
function updateCreateRestitutionSubmit() {
  const templateSel = document.getElementById("create-restitution-template");
  const participantSel = document.getElementById("create-restitution-participant");
  const filenameInput = document.getElementById("create-restitution-filename");
  const submitBtn = document.getElementById("create-restitution-submit");
  if (!templateSel || !participantSel || !filenameInput || !submitBtn) return;
  submitBtn.disabled = !templateSel.value || !participantSel.value || !filenameInput.value.trim();
}

// Propose un nom de fichier par défaut ("Restitution_Participant_Édition")
// quand le participant est choisi, sans écraser un nom déjà modifié à la
// main par l'utilisateur.
let lastAutoRestitutionFilename = "";

function updateDefaultRestitutionFilename() {
  const participantSel = document.getElementById("create-restitution-participant");
  const filenameInput = document.getElementById("create-restitution-filename");
  const popup = document.getElementById("create-restitution-popup");
  if (!participantSel || !filenameInput || !popup) return;

  const selected = participantSel.options[participantSel.selectedIndex];
  if (!selected || !selected.value) return;

  const participantName = selected.dataset.participantName || selected.textContent.trim();
  const editionLabel = popup.dataset.editionLabel || "";
  const defaultName = `Restitution_${participantName}_${editionLabel}`.replace(/\s+/g, "_");

  if (!filenameInput.value.trim() || filenameInput.value === lastAutoRestitutionFilename) {
    filenameInput.value = defaultName;
  }
  lastAutoRestitutionFilename = defaultName;
  updateCreateRestitutionSubmit();
}

["create-restitution-template", "create-restitution-participant", "create-restitution-filename"].forEach((id) => {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener("input", updateCreateRestitutionSubmit);
  el.addEventListener("change", updateCreateRestitutionSubmit);
});
const createRestitutionParticipantSel = document.getElementById("create-restitution-participant");
if (createRestitutionParticipantSel) {
  createRestitutionParticipantSel.addEventListener("change", updateDefaultRestitutionFilename);
}
updateCreateRestitutionSubmit();
