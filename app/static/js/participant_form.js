/*
 * Pré-remplissage de l'adresse de facturation avec l'adresse du participant,
 * tant que la case "Identique à l'adresse du participant" reste cochée.
 *
 * Important : on utilise `readOnly` (champs texte) et une classe CSS
 * "locked" (menu déroulant Pays) plutôt que l'attribut `disabled`, car les
 * champs désactivés avec `disabled` ne sont PAS envoyés lors de la
 * soumission du formulaire — ce qui effacerait l'adresse de facturation.
 */
document.addEventListener("DOMContentLoaded", function () {
  var sameCheckbox = document.getElementById("same_address");
  if (!sameCheckbox) return;

  var pairs = [
    ["pa_address1", "ba_address1"],
    ["pa_address2", "ba_address2"],
    ["pa_city", "ba_city"],
    ["pa_postal", "ba_postal"],
    ["pa_country", "ba_country"],
  ];

  function syncBilling() {
    pairs.forEach(function (pair) {
      var src = document.getElementById(pair[0]);
      var dst = document.getElementById(pair[1]);
      if (src && dst) dst.value = src.value;
    });
  }

  function setBillingLocked(locked) {
    pairs.forEach(function (pair) {
      var dst = document.getElementById(pair[1]);
      if (!dst) return;
      if (dst.tagName === "SELECT") {
        dst.classList.toggle("locked", locked);
      } else {
        dst.readOnly = locked;
      }
    });
  }

  function updateState() {
    if (sameCheckbox.checked) {
      syncBilling();
      setBillingLocked(true);
    } else {
      setBillingLocked(false);
    }
  }

  sameCheckbox.addEventListener("change", updateState);

  pairs.forEach(function (pair) {
    var src = document.getElementById(pair[0]);
    if (!src) return;
    src.addEventListener("input", function () {
      if (sameCheckbox.checked) syncBilling();
    });
    src.addEventListener("change", function () {
      if (sameCheckbox.checked) syncBilling();
    });
  });

  updateState();
});
