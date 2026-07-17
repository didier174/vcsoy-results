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
    if (priceInput) {
      priceInput.value = "";
      priceInput.disabled = true;
    }
    if (qtyInput) {
      qtyInput.value = "";
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

  document.getElementById("edit-invoice-popup").showModal();
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
});
