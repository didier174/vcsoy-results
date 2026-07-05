/*
 * Active/désactive le champ de montant d'un produit selon que sa case est
 * cochée ou non. Le champ désactivé n'étant pas soumis avec le
 * formulaire, c'est sans conséquence ici puisque le serveur ignore de
 * toute façon le montant des produits non sélectionnés.
 */
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".product-checkbox").forEach(function (checkbox) {
    var priceInput = document.getElementById("price_" + checkbox.dataset.productId);
    if (!priceInput) return;

    function update() {
      priceInput.disabled = !checkbox.checked;
    }

    checkbox.addEventListener("change", update);
    update();
  });

  // --- Auto-remplissage du nom du client et de l'adresse de facturation
  // (page de création) à partir du participant sélectionné. Reste
  // modifiable ensuite par l'utilisateur.
  var participantSelect = document.getElementById("participant_id");
  var participantsDataEl = document.getElementById("participants-data");
  if (participantSelect && participantsDataEl) {
    var participantsData = JSON.parse(participantsDataEl.textContent);

    participantSelect.addEventListener("change", function () {
      var info = participantsData[participantSelect.value];
      if (!info) return;

      var customerNameInput = document.getElementById("customer_name");
      if (customerNameInput) customerNameInput.value = info.name;

      var fieldMap = {
        bill_to_address1: "address1",
        bill_to_address2: "address2",
        bill_to_city: "city",
        bill_to_postal_code: "postal_code",
        bill_to_country: "country",
        bill_to_contact_name: "contact_name",
      };
      Object.keys(fieldMap).forEach(function (elementId) {
        var el = document.getElementById(elementId);
        if (el) el.value = info[fieldMap[elementId]] || "";
      });
    });
  }
});
