/*
 * Gère le popup "Modifier la facture" sur la page de liste des factures.
 * Toutes les données nécessaires sont déjà présentes sur la page (une
 * balise JSON par facture), donc aucun aller-retour réseau n'est
 * nécessaire pour ouvrir et pré-remplir le popup.
 */

function _getInvoiceData(invoiceId) {
  var el = document.getElementById("invoice-data-" + invoiceId);
  return el ? JSON.parse(el.textContent) : null;
}

function _resetEditProducts() {
  document.querySelectorAll(".edit-product-checkbox").forEach(function (checkbox) {
    checkbox.checked = false;
    var priceInput = document.getElementById("edit_price_" + checkbox.dataset.productId);
    if (priceInput) {
      priceInput.value = "";
      priceInput.disabled = true;
    }
  });
}

function openEditInvoiceDialog(invoiceId) {
  var data = _getInvoiceData(invoiceId);
  if (!data) return;

  var form = document.getElementById("edit-invoice-form");
  form.action = "/invoicing/" + invoiceId + "/update";

  document.getElementById("edit_language").value = data.language;
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
    var priceInput = document.getElementById("edit_price_" + item.product_id);
    if (priceInput) {
      priceInput.value = item.unit_price;
      priceInput.disabled = false;
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

document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".edit-product-checkbox").forEach(function (checkbox) {
    checkbox.addEventListener("change", function () {
      var priceInput = document.getElementById("edit_price_" + checkbox.dataset.productId);
      if (priceInput) priceInput.disabled = !checkbox.checked;
    });
  });
});
