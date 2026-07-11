// Tri (toujours croissant) de la liste de résultats de recherche, en
// cliquant sur l'en-tête d'une colonne (Test, Catégorie, Participant,
// Canal, Date). Les données sont déjà toutes présentes sur la page.
function sortSearchResults(key) {
  const container = document.querySelector(".table-card");
  if (!container) return;
  const rows = [...container.querySelectorAll(".search-result-row")];
  rows.sort((a, b) => (a.dataset[key] || "").localeCompare(b.dataset[key] || "", "fr", { numeric: true, sensitivity: "base" }));
  rows.forEach((row) => container.appendChild(row));
}

document.querySelectorAll(".table-sort-btn").forEach((btn) => {
  btn.addEventListener("click", () => sortSearchResults(btn.dataset.sortKey));
});
