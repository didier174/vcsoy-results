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

Certains records ne sont que des captures d'écran (ex. conversation de
chat) sans AUCUNE couche de texte sélectionnable — page.search_for ne
peut alors rien y trouver, quel que soit le nom saisi. Dans ce cas, la
page est rendue en image et passée à un moteur OCR (RapidOCR) pour
retrouver le texte ET sa position, puis apply_redactions(images=2,
valeur par défaut) efface réellement les pixels de l'image sous le
rectangle trouvé — pas un simple cache dessiné par-dessus (voir demande
explicite : caviardage réussi, avec OCR, sur un record de ce type).

RapidOCR peut planter NATIVEMENT (segfault, observé en pratique sur une
image sans texte détecté — cas très fréquent, ex. une page presque
blanche) — un crash qu'un try/except Python ne peut PAS intercepter, et
qui tuerait tout le worker web s'il avait lieu dans son propre
processus. L'inférence OCR tourne donc dans un PROCESSUS SÉPARÉ (voir
_ocr_images) : un crash n'y coûte que cette page (traitée comme "rien
trouvé"), jamais la stabilité du serveur.
"""

import io
import re
import time
import unicodedata
from multiprocessing import get_context

import pymupdf

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

BLACKOUT_FILL = (0, 0, 0)
MASK_FILL = (1, 1, 1)
MASK_TEXT_COLOR = (0, 0, 0)
MASK_FONTSIZE = 8

# Zoom appliqué au rendu de la page avant OCR. 2.0 (~144 dpi) manquait
# des mots pourtant nets à l'œil (ex. "VALARS" en petite police dans une
# capture de chat, retrouvé de façon fiable à partir de 3.0) — mesuré
# sur un vrai record avant de fixer cette valeur. Coût : ~2-3s/page.
OCR_ZOOM = 3.0

# Délai maximal accordé au processus OCR d'UNE page (un processus par
# page, voir _ocr_image) avant qu'on abandonne cette page (traitée
# comme "rien trouvé").
OCR_TOTAL_TIMEOUT = 45
# Granularité de sondage de la file de résultats — courte pour détecter
# un processus mort presque immédiatement plutôt que d'attendre le
# budget entier (voir _ocr_images).
OCR_POLL_INTERVAL = 0.5


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


def _pixmap_to_array(pix):
    import numpy as np
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = img[:, :, :3]
    elif pix.n == 1:
        img = np.repeat(img, 3, axis=2)
    return img.copy()  # copie contiguë ET modifiable — un buffer en
    # lecture seule (frombuffer) a provoqué un segfault dans le moteur OCR


def _render_page_for_ocr(page):
    """Rend la page en image (voir OCR_ZOOM), dans CE processus — seule
    l'inférence OCR elle-même tourne isolée (voir _ocr_images)."""
    return _pixmap_to_array(page.get_pixmap(matrix=pymupdf.Matrix(OCR_ZOOM, OCR_ZOOM)))


def _ocr_worker(img, result_queue):
    """Exécuté dans un PROCESSUS SÉPARÉ, un par page (voir _ocr_image) :
    un crash natif du moteur OCR ne tue alors que ce processus, jamais le
    worker web. Un processus PAR PAGE plutôt qu'un seul pour tout le
    document — mesuré sur un vrai record : sur un serveur à mémoire
    limitée, un unique processus qui charge le moteur puis traite page
    après page peut accumuler assez de mémoire (modèles + images) pour
    dépasser la limite et faire tuer toute l'instance. Un processus qui
    se termine complètement après chaque page rend systématiquement sa
    mémoire à l'OS entre deux pages.

    onnxruntime et OpenCV allouent par défaut UN THREAD PAR CŒUR
    disponible, chacun avec ses propres tampons — sur un serveur à
    plusieurs cœurs, ça peut consommer nettement plus de mémoire que
    sur un poste de développement à moins de cœurs actifs. On force ici
    un seul thread pour chacun (léger surcoût de temps, sans commune
    mesure avec l'enjeu de stabilité du serveur)."""
    try:
        import cv2
        cv2.setNumThreads(1)

        import onnxruntime as ort
        _base_session_options = ort.SessionOptions

        class _SingleThreadSessionOptions(_base_session_options):
            def __init__(self):
                super().__init__()
                self.intra_op_num_threads = 1
                self.inter_op_num_threads = 1

        ort.SessionOptions = _SingleThreadSessionOptions

        from rapidocr_onnxruntime import RapidOCR
        result, _elapse = RapidOCR()(img)
    except Exception:
        result = None
    result_queue.put(result)


def _ocr_image(img):
    """Reconnaissance de texte sur UNE image de page, isolée dans son
    propre processus (voir _ocr_worker). Retourne None si l'OCR a
    échoué, planté ou n'a pas répondu dans le budget (voir
    OCR_TOTAL_TIMEOUT) — le reste du caviardage de cette page (texte
    natif) n'est jamais perdu pour autant.

    Sonde la file par petits intervalles (OCR_POLL_INTERVAL) plutôt que
    d'attendre un long timeout d'un coup : un processus mort (plantage)
    est ainsi détecté quasi immédiatement plutôt que d'immobiliser la
    requête jusqu'au bout du délai."""
    ctx = get_context("spawn")
    result_queue = ctx.Queue()
    proc = ctx.Process(target=_ocr_worker, args=(img, result_queue), daemon=True)
    proc.start()
    try:
        result = None
        deadline = time.monotonic() + OCR_TOTAL_TIMEOUT
        while time.monotonic() < deadline:
            try:
                result = result_queue.get(timeout=OCR_POLL_INTERVAL)
                break
            except Exception:
                if not proc.is_alive():
                    break  # processus mort : rien de plus à en attendre
        return result
    finally:
        proc.join(timeout=5)
        if proc.is_alive():
            proc.terminate()
            proc.join()


def _ocr_result_to_lines(page, result):
    """Convertit le résultat OCR brut d'une page en (rect, texte_ligne)
    en coordonnées PAGE (pas pixel) — une entrée par ligne détectée
    (RapidOCR ne fournit pas de boîte par mot, voir _substring_rect pour
    l'estimation du sous-rectangle d'un nom à l'intérieur d'une ligne)."""
    lines = []
    for box, text, _score in result or []:
        xs = [pt[0] for pt in box]
        ys = [pt[1] for pt in box]
        rect = pymupdf.Rect(
            page.rect.x0 + min(xs) / OCR_ZOOM, page.rect.y0 + min(ys) / OCR_ZOOM,
            page.rect.x0 + max(xs) / OCR_ZOOM, page.rect.y0 + max(ys) / OCR_ZOOM,
        )
        lines.append((rect, text))
    return lines


def _find_spans(folded_text, folded_term):
    """Positions (start, end) de `folded_term` dans `folded_text` —
    valables tel quel sur le texte D'ORIGINE non replié, _fold produisant
    toujours un caractère en sortie pour un caractère en entrée."""
    spans = []
    if not folded_term:
        return spans
    start = 0
    while True:
        idx = folded_text.find(folded_term, start)
        if idx == -1:
            break
        spans.append((idx, idx + len(folded_term)))
        start = idx + 1
    return spans


def _substring_rect(line_rect, line_len, start, end, pad_frac=0.015):
    """Estime le rectangle de line_text[start:end] à l'intérieur de
    line_rect par simple proportion de caractères — la boîte OCR couvre
    la ligne ENTIÈRE, pas le mot seul ; sans cette estimation, caviarder
    un nom noircirait tout le message qui le contient. Léger padding
    pour absorber l'approximation (polices non monospaces)."""
    if line_len == 0:
        return line_rect
    width = line_rect.width
    pad = width * pad_frac
    x0 = max(line_rect.x0, line_rect.x0 + width * (start / line_len) - pad)
    x1 = min(line_rect.x1, line_rect.x0 + width * (end / line_len) + pad)
    return pymupdf.Rect(x0, line_rect.y0, x1, line_rect.y1)


def _ocr_blackout(page, lines, terms_by_field, found_by_field):
    """Caviarde, dans les images de la page, le texte introuvable dans sa
    couche de texte (voir module docstring), à partir des lignes déjà
    reconnues par OCR (voir _ocr_result_to_lines). Marque
    found_by_field[field] à True dès qu'une occurrence est trouvée par ce
    biais."""
    for rect, text in lines:
        folded_text = _fold(text)
        for field, terms in terms_by_field.items():
            for term in terms:
                for start, end in _find_spans(folded_text, _fold(term)):
                    sub_rect = _substring_rect(rect, len(text), start, end)
                    page.add_redact_annot(sub_rect, fill=BLACKOUT_FILL)
                    found_by_field[field] = True
        for m in EMAIL_RE.finditer(text):
            sub_rect = _substring_rect(rect, len(text), m.start(), m.end())
            page.add_redact_annot(
                sub_rect, text=_mask_email(m.group(0)), fill=MASK_FILL,
                text_color=MASK_TEXT_COLOR, fontsize=MASK_FONTSIZE,
            )


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

            # Texte présent UNIQUEMENT dans une image (capture d'écran) :
            # la couche de texte ci-dessus ne peut rien y trouver — OCR en
            # complément (module docstring). Rendu ET OCR de la page ICI,
            # une à la fois (jamais toutes les pages du document en
            # mémoire à la fois — voir _ocr_worker).
            ocr_result = _ocr_image(_render_page_for_ocr(page))
            if ocr_result:
                lines = _ocr_result_to_lines(page, ocr_result)
                _ocr_blackout(page, lines, terms_by_field, found_by_field)

            page.apply_redactions()  # images=2 (défaut) : pixels réellement effacés, pas un cache par-dessus

        out = io.BytesIO()
        # garbage=4 (purge les objets devenus inutiles, ex. images
        # remplacées) + deflate=True (recompresse les flux) : sans ça,
        # apply_redactions(images=2) réembarque les images caviardées de
        # façon quasi brute et le fichier peut être 60x plus gros (mesuré
        # sur un vrai record : 360 Ko -> 23 Mo sans ces options).
        doc.save(out, garbage=4, deflate=True)
        not_found = {field: bool(terms_by_field[field]) and not found_by_field[field] for field in names_by_field}
        return out.getvalue(), not_found
    finally:
        doc.close()
