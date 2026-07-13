/*
 * Bascule la case "Act Ref." d'un participant directement au clic, sans
 * recharger manuellement ni dépendre d'un <form> (un <form> par ligne,
 * imbriqué dans le grand <form> du tableau, est invalide en HTML et casse
 * la soumission du reste de la page — d'où cette approche par fetch()).
 */
document.addEventListener("DOMContentLoaded", function () {
  var csrfInput = document.querySelector('input[name="csrf_token"]');
  var csrfToken = csrfInput ? csrfInput.value : "";

  document.querySelectorAll(".act-ref-toggle").forEach(function (checkbox) {
    checkbox.addEventListener("change", function () {
      var participantId = checkbox.getAttribute("data-participant-id");
      checkbox.disabled = true;
      fetch("/participants/toggle_active/" + participantId, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken },
      })
        .then(function () {
          window.location.reload();
        })
        .catch(function () {
          window.location.reload();
        });
    });
  });

  // Tri (toujours croissant) de la liste par "Category Name" ou "Code" en
  // cliquant sur l'en-tête correspondant. Les lignes sont déjà toutes
  // présentes sur la page.
  document.querySelectorAll(".table-sort-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var key = btn.getAttribute("data-sort-key");
      var container = document.querySelector(".table-card");
      if (!container) return;
      var rows = Array.prototype.slice.call(container.querySelectorAll(".table-row:not(.table-header)"));
      rows.sort(function (a, b) {
        return (a.dataset[key] || "").localeCompare(b.dataset[key] || "", "fr", { numeric: true, sensitivity: "base" });
      });
      rows.forEach(function (row) {
        container.appendChild(row);
      });
    });
  });
});
