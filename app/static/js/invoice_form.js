/*
 * Active/désactive les champs de montant (et, pour les produits du
 * catalogue, de quantité) d'un produit selon que sa case est cochée ou
 * non. Un champ désactivé n'étant pas soumis avec le formulaire, c'est
 * sans conséquence ici puisque le serveur ignore de toute façon les
 * produits non sélectionnés.
 */
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".product-checkbox").forEach(function (checkbox) {
    var row = checkbox.closest(".product-row");
    var priceInput = row ? row.querySelector(".product-price-input") : null;
    var qtyInput = row ? row.querySelector(".product-qty-input") : null;

    function update() {
      if (priceInput) priceInput.disabled = !checkbox.checked;
      if (qtyInput) qtyInput.disabled = !checkbox.checked;
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

  // --- Récapitulatif de confirmation avant génération de la facture :
  // on intercepte la soumission une première fois pour afficher un
  // résumé des produits sélectionnés, puis on laisse passer une fois
  // l'utilisateur confirmé (flag sur le formulaire).
  var createForm = document.getElementById("invoice-create-form");
  var confirmPopup = document.getElementById("confirm-invoice-popup");
  var confirmSubmit = document.getElementById("confirm-invoice-submit");
  if (createForm && confirmPopup && confirmSubmit) {
    createForm.addEventListener("submit", function (e) {
      if (createForm.dataset.confirmed === "1") return;
      e.preventDefault();
      document.getElementById("invoice-summary-content").innerHTML = _buildInvoiceSummaryHtml();
      confirmPopup.showModal();
    });

    confirmSubmit.addEventListener("click", function () {
      confirmPopup.close();
      createForm.dataset.confirmed = "1";
      if (createForm.requestSubmit) {
        createForm.requestSubmit();
      } else {
        createForm.submit();
      }
    });
  }
});

function _buildInvoiceSummaryHtml() {
  var rows = [];
  var subtotal = 0;

  document.querySelectorAll(".product-checkbox:checked").forEach(function (checkbox) {
    var row = checkbox.closest(".product-row");
    if (!row) return;
    var labelEl = row.querySelector(".product-checkbox-label");
    var priceInput = row.querySelector(".product-price-input");
    var qtyInput = row.querySelector(".product-qty-input");

    var price = parseFloat(((priceInput && priceInput.value) || "0").replace(",", ".")) || 0;
    var qty = qtyInput ? (parseFloat(qtyInput.value) || 1) : 1;
    var total = price * qty;
    subtotal += total;

    rows.push({
      label: labelEl ? labelEl.textContent.trim() : "",
      qty: qty,
      price: price,
      total: total,
    });
  });

  var html = '<div class="compilation-table-wrap"><table class="compilation-table"><thead><tr>'
    + "<th>Produit</th><th>Qté</th><th>Prix unitaire</th><th>Total</th>"
    + "</tr></thead><tbody>";
  rows.forEach(function (r) {
    html += "<tr><td>" + r.label + "</td><td>" + r.qty + "</td><td>"
      + r.price.toFixed(2) + " $</td><td>" + r.total.toFixed(2) + " $</td></tr>";
  });
  html += "</tbody></table></div>";
  html += '<p class="muted" style="margin-top: 10px;">Sous-total avant taxes : <strong>'
    + subtotal.toFixed(2) + " $</strong> (les taxes exactes sont calculées à la génération).</p>";
  return html;
}
