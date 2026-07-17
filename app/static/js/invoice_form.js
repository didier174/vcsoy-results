/*
 * Active/désactive les champs de montant (et, pour les produits du
 * catalogue, de quantité) d'un produit selon que sa case est cochée ou
 * non. Un champ désactivé n'étant pas soumis avec le formulaire, c'est
 * sans conséquence ici puisque le serveur ignore de toute façon les
 * produits non sélectionnés.
 */
/*
 * Un produit du catalogue n'appartient qu'à une seule langue (fr ou en) :
 * on n'affiche (et ne rend sélectionnable) que les produits correspondant
 * à la langue de facture actuellement choisie. Décoche et désactive
 * automatiquement un produit masqué par le changement de langue.
 */
function _applyProductLanguageFilter(languageSelectEl) {
  if (!languageSelectEl) return;
  var lang = languageSelectEl.value;
  document.querySelectorAll(".product-entry").forEach(function (entry) {
    var entryLang = entry.dataset.language;
    var visible = !entryLang || !lang || entryLang === lang;
    entry.style.display = visible ? "" : "none";
    if (!visible) {
      var checkbox = entry.querySelector(".product-checkbox");
      if (checkbox && checkbox.checked) {
        checkbox.checked = false;
        checkbox.dispatchEvent(new Event("change"));
      }
    }
  });
}

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

  var languageSelect = document.getElementById("language");
  if (languageSelect) {
    _applyProductLanguageFilter(languageSelect);
    languageSelect.addEventListener("change", function () {
      _applyProductLanguageFilter(languageSelect);
    });
  }

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
      _renderConfirmSummary();
      confirmPopup.showModal();
    });

    confirmSubmit.addEventListener("click", function () {
      var orderInput = document.getElementById("product_order");
      if (orderInput) orderInput.value = _confirmCatalogOrder.join(",");
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

/*
 * Récapitulatif de confirmation : le VCSOY (s'il est sélectionné) figure
 * toujours en tête, non réordonnable (produit unique et indissociable, à
 * une position fixe dans le générateur). Les produits du catalogue sont
 * listés par ordre alphabétique par défaut, avec des flèches pour que
 * l'utilisateur choisisse lui-même l'ordre dans lequel ils apparaîtront
 * sur la facture — cet ordre est envoyé au serveur via product_order.
 */
var _confirmCatalogOrder = [];

function _collectCheckedProducts() {
  var vcsoy = null;
  var catalog = [];
  document.querySelectorAll(".product-checkbox:checked").forEach(function (checkbox) {
    var row = checkbox.closest(".product-row");
    if (!row) return;
    var labelEl = row.querySelector(".product-checkbox-label");
    var priceInput = row.querySelector(".product-price-input");
    var qtyInput = row.querySelector(".product-qty-input");
    var price = parseFloat(((priceInput && priceInput.value) || "0").replace(",", ".")) || 0;
    var qty = qtyInput ? (parseInt(qtyInput.value, 10) || 1) : 1;
    var item = {
      id: checkbox.dataset.productId,
      label: labelEl ? labelEl.textContent.trim() : "",
      qty: qty, price: price, total: price * qty,
    };
    if (checkbox.dataset.productId === "vcsoy_package") {
      vcsoy = item;
    } else {
      catalog.push(item);
    }
  });
  return { vcsoy: vcsoy, catalog: catalog };
}

function _moveConfirmProduct(id, direction) {
  var idx = _confirmCatalogOrder.indexOf(id);
  if (idx === -1) return;
  var newIdx = idx + direction;
  if (newIdx < 0 || newIdx >= _confirmCatalogOrder.length) return;
  var tmp = _confirmCatalogOrder[idx];
  _confirmCatalogOrder[idx] = _confirmCatalogOrder[newIdx];
  _confirmCatalogOrder[newIdx] = tmp;
  _renderConfirmSummary();
}

function _renderConfirmSummary() {
  var collected = _collectCheckedProducts();
  var byId = {};
  collected.catalog.forEach(function (item) { byId[item.id] = item; });

  // Conserve l'ordre déjà choisi pour les produits toujours cochés, retire
  // ceux décochés depuis, et ajoute les nouveaux (alphabétique, l'ordre du
  // catalogue) à la fin.
  var orderedIds = _confirmCatalogOrder.filter(function (id) { return byId[id]; });
  collected.catalog.forEach(function (item) {
    if (orderedIds.indexOf(item.id) === -1) orderedIds.push(item.id);
  });
  _confirmCatalogOrder = orderedIds;

  var subtotal = 0;
  var html = '<div class="compilation-table-wrap"><table class="compilation-table"><thead><tr>'
    + "<th></th><th>Produit</th><th>Qté</th><th>Prix unitaire</th><th>Total</th>"
    + "</tr></thead><tbody>";

  if (collected.vcsoy) {
    subtotal += collected.vcsoy.total;
    html += "<tr><td></td><td>" + collected.vcsoy.label + "</td><td>" + collected.vcsoy.qty + "</td><td>"
      + collected.vcsoy.price.toFixed(2) + " $</td><td>" + collected.vcsoy.total.toFixed(2) + " $</td></tr>";
  }

  _confirmCatalogOrder.forEach(function (id, index) {
    var item = byId[id];
    subtotal += item.total;
    var upAttrs = index === 0 ? "disabled" : "";
    var downAttrs = index === _confirmCatalogOrder.length - 1 ? "disabled" : "";
    html += "<tr><td class=\"invoice-order-controls\">"
      + "<button type=\"button\" class=\"btn-order-move\" " + upAttrs + " onclick=\"_moveConfirmProduct('" + id + "', -1)\">&#9650;</button>"
      + "<button type=\"button\" class=\"btn-order-move\" " + downAttrs + " onclick=\"_moveConfirmProduct('" + id + "', 1)\">&#9660;</button>"
      + "</td><td>" + item.label + "</td><td>" + item.qty + "</td><td>"
      + item.price.toFixed(2) + " $</td><td>" + item.total.toFixed(2) + " $</td></tr>";
  });

  html += "</tbody></table></div>";
  if (collected.vcsoy) {
    html += '<p class="muted" style="margin-top: 6px;">Le produit VCSOY figure toujours en tête de la facture.</p>';
  }
  if (_confirmCatalogOrder.length > 1) {
    html += '<p class="muted" style="margin-top: 6px;">Utilisez les flèches pour changer l\'ordre des autres produits sur la facture.</p>';
  }
  html += '<p class="muted" style="margin-top: 10px;">Sous-total avant taxes : <strong>'
    + subtotal.toFixed(2) + " $</strong> (les taxes exactes sont calculées à la génération).</p>";

  document.getElementById("invoice-summary-content").innerHTML = html;
}
