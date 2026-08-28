"""
Caviardage d'un record PDF pour « Caviarder des records » : retire du
contenu du PDF toute mention du nom du participant, des adresses e-mail
(ne laissant que la première lettre, l'arobase et l'extension) et,
lorsqu'ils sont renseignés par l'utilisateur, le nom du testeur (client
mystère) et celui du conseiller client qui l'a pris en charge — aucune de
ces deux informations n'existe nulle part en base sous forme structurée
(seulement en texte libre dans le PDF, s'il y figure), d'où la saisie
manuelle au moment du caviardage plutôt qu'une recherche automatique.

PyMuPDF (import pymupdf) est utilisé pour une VRAIE suppression du texte
(page.apply_redactions() retire le contenu du flux PDF sous le cache
noir, contrairement à un simple rectangle dessiné par-dessus qui laisse
le texte récupérable) — confirmé par un test dédié avant l'implémentation.

La recherche est insensible à la casse ET aux accents (voir
_find_actual_spellings) : un nom saisi sans ses accents (ex. "Francois"
pour "François", cas fréquent) est quand même retrouvé et caviardé avec
l'orthographe réelle du document.
"""

import io
import re
import unicodedata

import pymupdf

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

BLACKOUT_FILL = (0, 0, 0)
MASK_FILL = (1, 1, 1)
MASK_TEXT_COLOR = (0, 0, 0)
MASK_FONTSIZE = 8


def _mask_email(email):
    """"jean.dupont@example.com" -> "j***@***.com" (garde la première
    lettre, l'arobase et l'extension — voir demande explicite)."""
    local, _, domain = email.partition("@")
    first = local[0] if local else ""
    ext = domain.rsplit(".", 1)[-1] if "." in domain else domain
    return f"{first}***@***.{ext}"


def _name_search_terms(name):
    """Le nom complet, PLUS chaque mot pris isolément (ex. "Paul" seul
    apparaît parfois sans le nom de famille dans un échange) — voir
    demande explicite de l'utilisateur (exemple "Paul de MICHELIN").
    Espaces multiples réduits à un seul (la saisie utilisateur peut en
    contenir, le PDF non)."""
    name = re.sub(r"\s+", " ", (name or "").strip())
    if not name:
        return []
    terms = {name}
    terms.update(w for w in name.split() if len(w) > 1)
    return list(terms)


def _case_variants(term):
    return {term, term.upper(), term.lower(), term.title()}


def _fold_char(c):
    """Un caractère accentué -> sa base sans accent, TOUJOURS un seul
    caractère en sortie pour un caractère en entrée (indispensable pour
    retrouver, par position, la sous-chaîne d'origine — voir
    _find_actual_spellings)."""
    decomposed = unicodedata.normalize("NFKD", c)
    base = next((ch for ch in decomposed if not unicodedata.combining(ch)), c)
    return base.lower()


def _fold(text):
    return "".join(_fold_char(c) for c in text)


def _find_actual_spellings(page_text, term):
    """page.search_for a besoin de la chaîne EXACTE (accents compris)
    présente dans le PDF — or l'utilisateur saisit souvent un nom SANS
    les accents qu'il porte réellement dans le document (ex. "Francois"
    tapé pour "François"), ce qui faisait échouer silencieusement le
    caviardage (voir demande explicite : "le caviardage n'a pas eu
    lieu"). On cherche `term` dans le texte de la page en ignorant
    casse ET accents, puis on récupère la sous-chaîne d'origine (avec
    ses accents/sa casse réels) à chaque position trouvée."""
    folded_term = _fold(term)
    if not folded_term:
        return set()
    folded_page = _fold(page_text)
    spellings = set()
    start = 0
    while True:
        idx = folded_page.find(folded_term, start)
        if idx == -1:
            break
        spellings.add(page_text[idx:idx + len(term)])
        start = idx + 1
    return spellings


def _blackout_all(page, page_text, term):
    """Caviarde toutes les occurrences de `term` sur la page — y compris
    celles orthographiées avec des accents différents de la saisie (voir
    _find_actual_spellings). Retourne True si au moins une occurrence a
    été trouvée (et donc caviardée)."""
    hit = False
    for spelling in _find_actual_spellings(page_text, term) | {term}:
        for variant in _case_variants(spelling):
            for rect in page.search_for(variant):
                page.add_redact_annot(rect, fill=BLACKOUT_FILL)
                hit = True
    return hit


def redact_pdf(file_data, participant_name=None, tester_name=None, advisor_name=None):
    """Retourne (octets du PDF caviardé, noms_non_trouves) — le fichier
    d'origine (file_data) n'est jamais modifié, un nouveau document est
    ouvert à partir de ses octets et c'est LUI qui est caviardé puis
    sauvegardé séparément.

    `noms_non_trouves` est {"participant"|"testeur"|"conseiller": bool} :
    True si ce nom a été renseigné mais n'a été trouvé nulle part dans le
    document (aucune occurrence caviardée) — permet de prévenir
    l'utilisateur plutôt que de laisser croire, à tort, que le caviardage
    a eu lieu (voir demande explicite : "le caviardage n'a pas eu lieu
    sur mon test")."""
    names_by_field = {"participant": participant_name, "testeur": tester_name, "conseiller": advisor_name}
    terms_by_field = {field: _name_search_terms(name) for field, name in names_by_field.items()}
    found_by_field = {field: False for field in names_by_field}

    doc = pymupdf.open(stream=file_data, filetype="pdf")
    try:
        for page in doc:
            page_text = page.get_text()
            for field, terms in terms_by_field.items():
                for term in terms:
                    if _blackout_all(page, page_text, term):
                        found_by_field[field] = True

            emails = set(EMAIL_RE.findall(page_text))
            for email in emails:
                masked = _mask_email(email)
                for rect in page.search_for(email):
                    page.add_redact_annot(
                        rect, text=masked, fill=MASK_FILL, text_color=MASK_TEXT_COLOR, fontsize=MASK_FONTSIZE,
                    )

            page.apply_redactions()

        out = io.BytesIO()
        # garbage=4 (purge les objets devenus inutiles) + deflate=True
        # (recompresse les flux) : sans ça, apply_redactions() peut
        # réembarquer une image touchée par une redaction de façon quasi
        # brute et faire largement grossir le fichier.
        doc.save(out, garbage=4, deflate=True)
        not_found = {field: bool(terms_by_field[field]) and not found_by_field[field] for field in names_by_field}
        return out.getvalue(), not_found
    finally:
        doc.close()
