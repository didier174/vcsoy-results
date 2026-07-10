// Interception du clic sur "Ouvrir le record" : les PDF suivent le lien
// normal (nouvel onglet, visionneuse du navigateur) ; les fichiers audio
// sont lus dans une popup dédiée plutôt que d'ouvrir un nouvel onglet.
function openRecordLink(event, url, isAudio) {
  if (!isAudio) return;
  event.preventDefault();

  let dialog = document.getElementById("audio-record-popup");
  if (!dialog) {
    dialog = document.createElement("dialog");
    dialog.id = "audio-record-popup";
    dialog.className = "app-dialog";
    dialog.innerHTML =
      "<h3>Lecture du record</h3>" +
      '<audio id="audio-record-player" controls autoplay style="width: 100%; margin: 14px 0;"></audio>' +
      '<div class="dialog-actions">' +
      "<button type=\"button\" class=\"btn btn-secondary\" onclick=\"document.getElementById('audio-record-popup').close()\">Fermer</button>" +
      "</div>";
    document.body.appendChild(dialog);
    dialog.addEventListener("close", function () {
      const player = document.getElementById("audio-record-player");
      player.pause();
      player.removeAttribute("src");
      player.load();
    });
  }

  const player = document.getElementById("audio-record-player");
  player.src = url;
  dialog.showModal();
  player.play();
}
