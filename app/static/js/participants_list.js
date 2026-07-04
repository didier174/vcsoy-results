/*
 * Bascule la case "Act Ref." d'un participant directement au clic, sans
 * recharger manuellement ni dépendre d'un <form> (un <form> par ligne,
 * imbriqué dans le grand <form> du tableau, est invalide en HTML et casse
 * la soumission du reste de la page — d'où cette approche par fetch()).
 */
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".act-ref-toggle").forEach(function (checkbox) {
    checkbox.addEventListener("change", function () {
      var participantId = checkbox.getAttribute("data-participant-id");
      checkbox.disabled = true;
      fetch("/participants/toggle_active/" + participantId, { method: "POST" })
        .then(function () {
          window.location.reload();
        })
        .catch(function () {
          window.location.reload();
        });
    });
  });
});
