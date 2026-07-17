/*
 * Gère le popup "Modifier la facture" et le popup "Liste des produits"
 * (catalogue) sur la page de liste des factures. Toutes les données
 * nécessaires sont déjà présentes sur la page (une balise JSON par
 * facture, une balise JSON pour le catalogue), donc aucun aller-retour
 * réseau n'est nécessaire pour ouvrir et pré-remplir les popups.
 */

function _getInvoiceData(invoiceId) {
  var el = document.getElementById("invoice-data-" + invoiceId);
  return el ? JSON.parse(el.textContent) : null;
}

function _resetEditProducts() {
  document.querySelectorAll(".edit-product-checkbox").forEach(function (checkbox) {
    checkbox.checked = false;
    var row = checkbox.closest(".product-row");
    var priceInput = row ? row.querySelector(".product-price-input") : null;
    var qtyInput = row ? row.querySelector(".product-qty-input") : null;
    // Un produit non sélectionné retrouve son prix catalogue par défaut
    // (et quantité 1), comme sur la page de création — pas une valeur
    // vide — au cas où l'utilisateur le coche ensuite.
    if (priceInput) {
      priceInput.value = priceInput.dataset.defaultPrice || "";
      priceInput.disabled = true;
    }
    if (qtyInput) {
      qtyInput.value = qtyInput.dataset.defaultQty || "1";
      qtyInput.disabled = true;
    }
  });
}

/*
 * Un produit du catalogue n'appartient qu'à une seule langue (fr ou en) :
 * on n'affiche (et ne rend sélectionnable) que les produits correspondant
 * à la langue de facture actuellement choisie. Décoche et désactive
 * automatiquement un produit masqué par le changement de langue.
 */
function _applyProductLanguageFilter(languageSelectEl, entrySelector, checkboxSelector) {
  if (!languageSelectEl) return;
  var lang = languageSelectEl.value;
  document.querySelectorAll(entrySelector).forEach(function (entry) {
    var entryLang = entry.dataset.language;
    var visible = !entryLang || !lang || entryLang === lang;
    entry.style.display = visible ? "" : "none";
    if (!visible) {
      var checkbox = entry.querySelector(checkboxSelector);
      if (checkbox && checkbox.checked) {
        checkbox.checked = false;
        checkbox.dispatchEvent(new Event("change"));
      }
    }
  });
}

function openEditInvoiceDialog(invoiceId) {
  var data = _getInvoiceData(invoiceId);
  if (!data) return;

  var form = document.getElementById("edit-invoice-form");
  form.action = "/invoicing/" + invoiceId + "/update";
  // Repart à chaque ouverture sans confirmation : sinon, une fois la
  // première modification confirmée, les suivantes sauteraient le popup
  // de confirmation (le formulaire reste dans le DOM entre deux éditions).
  form.dataset.confirmed = "";

  var editLanguageSelect = document.getElementById("edit_language");
  editLanguageSelect.value = data.language;
  _applyProductLanguageFilter(editLanguageSelect, "#edit-invoice-popup .product-entry", ".edit-product-checkbox");
  document.getElementById("edit_invoice_number").value = data.invoice_number;
  document.getElementById("edit_customer_number").value = data.customer_number;
  document.getElementById("edit_customer_name").value = data.customer_name;
  document.getElementById("edit_invoice_date").value = data.invoice_date;
  document.getElementById("edit_bill_to_contact_name").value = data.bill_to_contact_name;
  document.getElementById("edit_bill_to_address1").value = data.bill_to_address1;
  document.getElementById("edit_bill_to_address2").value = data.bill_to_address2;
  document.getElementById("edit_bill_to_city").value = data.bill_to_city;
  document.getElementById("edit_bill_to_postal_code").value = data.bill_to_postal_code;
  document.getElementById("edit_bill_to_country").value = data.bill_to_country;

  _resetEditProducts();
  (data.products || []).forEach(function (item) {
    var checkbox = document.querySelector('.edit-product-checkbox[data-product-id="' + item.product_id + '"]');
    if (!checkbox) return;
    checkbox.checked = true;
    var row = checkbox.closest(".product-row");
    var priceInput = row ? row.querySelector(".product-price-input") : null;
    var qtyInput = row ? row.querySelector(".product-qty-input") : null;
    if (priceInput) {
      priceInput.value = item.unit_price;
      priceInput.disabled = false;
    }
    if (qtyInput) {
      qtyInput.value = item.quantity || 1;
      qtyInput.disabled = false;
    }
  });

  // Ordre déjà enregistré sur cette facture (celui du catalogue, hors
  // VCSOY) : point de départ du réordonnancement, plutôt que de repartir
  // de l'ordre alphabétique comme pour une facture neuve.
  _editCatalogOrder = (data.products || [])
    .filter(function (item) { return String(item.product_id) !== "vcsoy_package"; })
    .map(function (item) { return String(item.product_id); });

  document.getElementById("edit-invoice-popup").showModal();
}

/*
 * Récapitulatif de confirmation avant enregistrement d'une facture modifiée
 * (même principe que sur la page de création, voir invoice_form.js) : le
 * VCSOY reste toujours en tête, les produits du catalogue partent de
 * l'ordre déjà enregistré sur la facture (_editCatalogOrder, initialisé
 * dans openEditInvoiceDialog) et peuvent être réordonnés via des flèches.
 */
var _editCatalogOrder = [];

function _collectCheckedEditProducts() {
  var vcsoy = null;
  var catalog = [];
  document.querySelectorAll("#edit-invoice-form .edit-product-checkbox:checked").forEach(function (checkbox) {
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

function _moveEditConfirmProduct(id, direction) {
  var idx = _editCatalogOrder.indexOf(id);
  if (idx === -1) return;
  var newIdx = idx + direction;
  if (newIdx < 0 || newIdx >= _editCatalogOrder.length) return;
  var tmp = _editCatalogOrder[idx];
  _editCatalogOrder[idx] = _editCatalogOrder[newIdx];
  _editCatalogOrder[newIdx] = tmp;
  _renderEditConfirmSummary();
}

function _renderEditConfirmSummary() {
  var collected = _collectCheckedEditProducts();
  var byId = {};
  collected.catalog.forEach(function (item) { byId[item.id] = item; });

  var orderedIds = _editCatalogOrder.filter(function (id) { return byId[id]; });
  collected.catalog.forEach(function (item) {
    if (orderedIds.indexOf(item.id) === -1) orderedIds.push(item.id);
  });
  _editCatalogOrder = orderedIds;

  var subtotal = 0;
  var html = '<div class="compilation-table-wrap"><table class="compilation-table"><thead><tr>'
    + "<th></th><th>Produit</th><th>Qté</th><th>Prix unitaire</th><th>Total</th>"
    + "</tr></thead><tbody>";

  if (collected.vcsoy) {
    subtotal += collected.vcsoy.total;
    html += "<tr><td></td><td>" + collected.vcsoy.label + "</td><td>" + collected.vcsoy.qty + "</td><td>"
      + collected.vcsoy.price.toFixed(2) + " $</td><td>" + collected.vcsoy.total.toFixed(2) + " $</td></tr>";
  }

  _editCatalogOrder.forEach(function (id, index) {
    var item = byId[id];
    subtotal += item.total;
    var upAttrs = index === 0 ? "disabled" : "";
    var downAttrs = index === _editCatalogOrder.length - 1 ? "disabled" : "";
    html += "<tr><td class=\"invoice-order-controls\">"
      + "<button type=\"button\" class=\"btn-order-move\" " + upAttrs + " onclick=\"_moveEditConfirmProduct('" + id + "', -1)\">&#9650;</button>"
      + "<button type=\"button\" class=\"btn-order-move\" " + downAttrs + " onclick=\"_moveEditConfirmProduct('" + id + "', 1)\">&#9660;</button>"
      + "</td><td>" + item.label + "</td><td>" + item.qty + "</td><td>"
      + item.price.toFixed(2) + " $</td><td>" + item.total.toFixed(2) + " $</td></tr>";
  });

  html += "</tbody></table></div>";
  if (collected.vcsoy) {
    html += '<p class="muted" style="margin-top: 6px;">Le produit VCSOY figure toujours en tête de la facture.</p>';
  }
  if (_editCatalogOrder.length > 1) {
    html += '<p class="muted" style="margin-top: 6px;">Utilisez les flèches pour changer l\'ordre des autres produits sur la facture.</p>';
  }
  html += '<p class="muted" style="margin-top: 10px;">Sous-total avant taxes : <strong>'
    + subtotal.toFixed(2) + " $</strong> (les taxes exactes sont calculées à l'enregistrement).</p>";

  document.getElementById("edit-invoice-summary-content").innerHTML = html;
}

function triggerEditInvoice() {
  var checked = document.querySelectorAll(".invoice-select-checkbox:checked");
  if (checked.length === 0) {
    alert("Veuillez cocher une facture à modifier.");
    return;
  }
  if (checked.length > 1) {
    alert("Veuillez ne sélectionner qu'une seule facture à la fois pour la modification.");
    return;
  }
  openEditInvoiceDialog(checked[0].value);
}

/* ------------------------------------------------- Catalogue de produits */

function _getProductsData() {
  var el = document.getElementById("products-data");
  return el ? JSON.parse(el.textContent) : {};
}

function _updateCatalogButtonStates() {
  var checked = document.querySelectorAll(".catalog-select-checkbox:checked");
  var modifyBtn = document.getElementById("catalog-modify-btn");
  var deleteBtn = document.getElementById("catalog-delete-btn");
  if (modifyBtn) modifyBtn.disabled = checked.length !== 1;
  if (deleteBtn) deleteBtn.disabled = checked.length === 0;
}

function openAddProductDialog() {
  var form = document.getElementById("product-form");
  form.action = "/invoicing/products/add";
  document.getElementById("product-form-title").textContent = "Ajouter un produit";
  document.getElementById("product-form-title-input").value = "";
  document.getElementById("product-form-language").value = "";
  document.getElementById("product-form-bullet1").value = "";
  document.getElementById("product-form-bullet2").value = "";
  document.getElementById("product-form-bullet3").value = "";
  document.getElementById("product-form-price").value = "";
  document.getElementById("product-form-popup").showModal();
}

function triggerModifyProduct() {
  var checked = document.querySelectorAll(".catalog-select-checkbox:checked");
  if (checked.length !== 1) return;
  var productId = checked[0].value;
  var products = _getProductsData();
  var product = products[productId];
  if (!product) return;

  var form = document.getElementById("product-form");
  form.action = "/invoicing/products/" + productId + "/update";
  document.getElementById("product-form-title").textContent = "Modifier un produit";
  document.getElementById("product-form-title-input").value = product.title;
  document.getElementById("product-form-language").value = product.language;
  document.getElementById("product-form-bullet1").value = product.bullet1;
  document.getElementById("product-form-bullet2").value = product.bullet2;
  document.getElementById("product-form-bullet3").value = product.bullet3;
  document.getElementById("product-form-price").value = product.price;
  document.getElementById("product-form-popup").showModal();
}

document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".edit-product-checkbox").forEach(function (checkbox) {
    checkbox.addEventListener("change", function () {
      var row = checkbox.closest(".product-row");
      var priceInput = row ? row.querySelector(".product-price-input") : null;
      var qtyInput = row ? row.querySelector(".product-qty-input") : null;
      if (priceInput) priceInput.disabled = !checkbox.checked;
      if (qtyInput) qtyInput.disabled = !checkbox.checked;
    });
  });

  document.querySelectorAll(".catalog-select-checkbox").forEach(function (checkbox) {
    checkbox.addEventListener("change", _updateCatalogButtonStates);
  });
  _updateCatalogButtonStates();

  var editLanguageSelect = document.getElementById("edit_language");
  if (editLanguageSelect) {
    editLanguageSelect.addEventListener("change", function () {
      _applyProductLanguageFilter(editLanguageSelect, "#edit-invoice-popup .product-entry", ".edit-product-checkbox");
    });
  }

  var editForm = document.getElementById("edit-invoice-form");
  var editConfirmPopup = document.getElementById("edit-confirm-invoice-popup");
  var editConfirmSubmit = document.getElementById("edit-confirm-invoice-submit");
  if (editForm && editConfirmPopup && editConfirmSubmit) {
    editForm.addEventListener("submit", function (e) {
      if (editForm.dataset.confirmed === "1") return;
      e.preventDefault();
      _renderEditConfirmSummary();
      editConfirmPopup.showModal();
    });

    editConfirmSubmit.addEventListener("click", function () {
      var orderInput = document.getElementById("edit_product_order");
      if (orderInput) orderInput.value = _editCatalogOrder.join(",");
      editConfirmPopup.close();
      editForm.dataset.confirmed = "1";
      if (editForm.requestSubmit) {
        editForm.requestSubmit();
      } else {
        editForm.submit();
      }
    });
  }
});
