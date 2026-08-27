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
"""

import io
import re

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
    demande explicite de l'utilisateur (exemple "Paul de MICHELIN")."""
    name = (name or "").strip()
    if not name:
        return []
    terms = {name}
    terms.update(w for w in name.split() if len(w) > 1)
    return list(terms)


def _case_variants(term):
    return {term, term.upper(), term.lower(), term.title()}


def _blackout_all(page, term):
    for variant in _case_variants(term):
        for rect in page.search_for(variant):
            page.add_redact_annot(rect, fill=BLACKOUT_FILL)


def redact_pdf(file_data, participant_name=None, tester_name=None, advisor_name=None):
    """Retourne les octets du PDF caviardé. Le fichier d'origine (file_data)
    n'est jamais modifié — un nouveau document est ouvert à partir de ses
    octets et c'est LUI qui est caviardé puis sauvegardé séparément."""
    doc = pymupdf.open(stream=file_data, filetype="pdf")
    try:
        blackout_names = []
        for name in (participant_name, tester_name, advisor_name):
            blackout_names.extend(_name_search_terms(name))

        for page in doc:
            for term in blackout_names:
                _blackout_all(page, term)

            emails = set(EMAIL_RE.findall(page.get_text()))
            for email in emails:
                masked = _mask_email(email)
                for rect in page.search_for(email):
                    page.add_redact_annot(
                        rect, text=masked, fill=MASK_FILL, text_color=MASK_TEXT_COLOR, fontsize=MASK_FONTSIZE,
                    )

            page.apply_redactions()

        out = io.BytesIO()
        doc.save(out)
        return out.getvalue()
    finally:
        doc.close()
