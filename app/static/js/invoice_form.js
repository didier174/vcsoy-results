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
});
