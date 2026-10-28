"""
Met à jour les éléments visuels spécifiques au modèle de « Restitution »
(présentation de debrief par participant), qui ne sont pas de simples
balises {{ ... }} texte :

- diapositives 5/6/9/12/15/18 : graphique de comparaison (Vous / Catégorie /
  Ensemble des participants / Lauréats), note globale et par canal.
- diapositives 5/6/9/12/15/18 : graphique de classement (classement sur
  l'ensemble de l'édition, tous canaux confondus pour la diapo globale,
  canal par canal ensuite), sans trou entre le rang 1 et le participant
  (voir _ranking_window), avec sa barre mise en évidence à sa vraie
  position.
- diapositive 5 : texte "Classement Xème" (classement global de l'édition).
- diapositives 8/13/16/19/22 (« Focus » par canal) : répartition dynamique
  des critères listés dans le modèle en 2 colonnes (verte à gauche / rouge à
  droite) selon que la note du participant sur le critère est supérieure ou
  égale (vert) ou inférieure (rouge) à la note moyenne de ce critère pour tous
  les participants de l'édition (voir apply_criteria_split).

Ces graphiques sont des graphiques 3D (bar3DChart), un type non supporté
par l'API haut niveau de python-pptx (chart.plots/series lèvent une
exception) : on manipule donc leur XML directement, comme pour les
graphiques du rapport d'étude (voir app/reports/report_visuals.py), sans
dépendre de cette API pour ces graphiques précis.
"""

import re
from copy import deepcopy

from lxml import etree
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn

from app.results.presentation import CHANNEL_ORDER
from app.results.scoring import CRITERIA_BY_CHANNEL, DOUBLED_CODE_BY_CHANNEL

# Diapositive (0-based) portant le graphique de comparaison + le graphique
# de classement pour chaque portée (note globale, puis chaque canal).
COMPARISON_SLIDE_BY_SCOPE = {"global": 4, "phone": 5, "mail": 8, "web": 11, "rs": 14, "chat": 17}

# Diapositive (0-based) portant la répartition verte/rouge des critères,
# une par canal (la diapo globale n'a pas de détail par critère).
CRITERIA_SLIDE_BY_CHANNEL = {"phone": 7, "mail": 12, "web": 15, "rs": 18, "chat": 21}

# Nom court par code de critère et par canal, repris tel quel des étiquettes
# déjà utilisées dans le mapping d'importance du rapport d'étude (voir
# report_visuals.MAPPING_POINT_CODE) — le critère "Impression générale" en
# est systématiquement absent (choix déjà fait dans ce mapping), complété
# ici à partir du libellé du récapitulatif des critères du rapport d'étude.
CRITERION_SHORT_NAMES = {
    "phone": {
        1: "Accueil par le conseiller", 2: "Accueil SVI", 3: "Utilisation d'un vocabulaire adapté",
        4: "Reformulation de la demande", 5: "Transfert", 6: "Écoute", 7: "Prise de congé",
        8: "Temps de décroché", 9: "Prise en charge du contact par un conseiller",
        10: "Accès au service désiré (SVI)", 11: "Réponse différée", 12: "Mise en attente",
        13: "Qualité de la réponse", 14: "Impression générale", 15: "Qualité du ton",
    },
    "mail": {
        1: "Expéditeur", 2: "Objet", 3: "Personnalisation de la réponse", 4: "Qualité de rédaction",
        5: "Résumé de la situation", 6: "Conclusion", 7: "Identification", 8: "Poursuite de la relation",
        9: "Temps de réponse", 10: "Accusé de réception", 11: "Qualité de la réponse",
        12: "Impression générale", 13: "Ton employé", 14: "Lisibilité",
    },
    "web": {
        1: "Visibilité", 2: "Fonctionnalité", 3: "Efficacité", 4: "Rétroactivité", 5: "Attractivité",
        6: "Identification", 7: "Réponse concise", 8: "Savoir faire", 9: "Savoir dire",
        10: "Poursuite de la relation", 11: "Qualité de la réponse", 12: "Impression générale",
        13: "Lisibilité",
    },
    "rs": {
        1: "Identification du participant", 2: "Coordonnées du Participant", 3: "Personnalisation",
        4: "Rédaction", 5: "Forme de la réponse", 6: "Prise de congé",
        7: "Identification de l'interlocuteur", 8: "Poursuite de la relation", 9: "Temps de la réponse",
        10: "Message relais", 11: "Qualité de la réponse", 12: "Fonctionnalité du lien",
        13: "Impression générale", 14: "Ton employé", 15: "Savoir Faire",
    },
    "chat": {
        1: "Visibilité", 2: "Temps de prise en charge", 3: "Réactivité", 4: "Accueil",
        5: "Personnalisation", 6: "Rédaction", 7: "Prise de congé", 8: "Forme de la réponse",
        9: "Fonctionnalité du lien", 10: "Qualité de la réponse", 11: "Lisibilité",
        12: "Historique de conversation", 13: "Impression générale", 14: "Ton employé",
    },
}

RANKING_WINDOW_SIZE = 8
HIGHLIGHT_COLOR = "00B2E6"
OTHER_COLOR = "7F7F7F"


def _as_float(value):
    """Convertit une valeur de `values` (float brut, ou chaîne déjà
    formatée par report_data._fmt_note/_fmt_pct, ex. "12,34" ou "45%") en
    float, ou None si absente/non calculable ("—")."""
    if value is None or value == "—":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().rstrip("%").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


# --------------------------------------------------------- Lecture du XML

def _find_chart_ser_by_marker(slide, marker):
    """Retourne (chartspace, ser, cat_strCache, val_numCache) du premier
    graphique de la diapo dont au moins une catégorie contient `marker`
    (ex. "Catégorie" pour le graphique de comparaison, "Participant" pour
    le classement)."""
    for shape in slide.shapes:
        if not getattr(shape, "has_chart", False):
            continue
        try:
            cs = shape.chart._chartSpace
        except Exception:
            continue
        ser = cs.find(f".//{qn('c:ser')}")
        if ser is None:
            continue
        cat = ser.find(qn("c:cat"))
        if cat is None:
            continue
        cat_values = [v.text or "" for v in cat.findall(f".//{qn('c:v')}")]
        if any(marker in v for v in cat_values):
            strcache = cat.find(f".//{qn('c:strCache')}")
            val_el = ser.find(qn("c:val"))
            numcache = val_el.find(f".//{qn('c:numCache')}") if val_el is not None else None
            return cs, ser, strcache, numcache
    return None, None, None, None


# Marge (en points sur 20) ajoutée de part et d'autre des valeurs
# réellement affichées pour calibrer l'axe des ordonnées de chaque
# histogramme — bien plus resserré que la plage fixe du modèle (souvent
# 0-20 ou 8-20), pour que les écarts entre barres restent visibles à l'œil
# même quand toutes les notes sont proches les unes des autres.
AXIS_PADDING = 1.0
AXIS_FLOOR, AXIS_CEIL = 0.0, 20.0


def _set_value_axis_range(chartspace, values):
    values = [v for v in values if v is not None]
    if not values:
        return
    axis = chartspace.find(f".//{qn('c:valAx')}")
    if axis is None:
        return
    lo = max(AXIS_FLOOR, min(values) - AXIS_PADDING)
    hi = min(AXIS_CEIL, max(values) + AXIS_PADDING)
    if hi - lo < 2:  # évite un axe dégénéré si toutes les valeurs sont quasi identiques
        mid = (lo + hi) / 2
        lo, hi = max(AXIS_FLOOR, mid - 1), min(AXIS_CEIL, mid + 1)
    min_el = axis.find(f".//{qn('c:min')}")
    max_el = axis.find(f".//{qn('c:max')}")
    if min_el is not None:
        min_el.set("val", repr(round(lo, 1)))
    if max_el is not None:
        max_el.set("val", repr(round(hi, 1)))


def _set_str_cache(strcache_el, values):
    if strcache_el is None:
        return
    for pt in list(strcache_el.findall(qn("c:pt"))):
        strcache_el.remove(pt)
    ptcount = strcache_el.find(qn("c:ptCount"))
    if ptcount is not None:
        ptcount.set("val", str(len(values)))
    for idx, value in enumerate(values):
        pt = etree.SubElement(strcache_el, qn("c:pt"))
        pt.set("idx", str(idx))
        v_el = etree.SubElement(pt, qn("c:v"))
        v_el.text = str(value)


def _set_num_cache(numcache_el, values):
    if numcache_el is None:
        return
    for pt in list(numcache_el.findall(qn("c:pt"))):
        numcache_el.remove(pt)
    ptcount = numcache_el.find(qn("c:ptCount"))
    if ptcount is not None:
        ptcount.set("val", str(len(values)))
    for idx, value in enumerate(values):
        pt = etree.SubElement(numcache_el, qn("c:pt"))
        pt.set("idx", str(idx))
        v_el = etree.SubElement(pt, qn("c:v"))
        v_el.text = repr(float(value))


def _recolor_dpt(dpt, color_hex):
    fill = dpt.find(f".//{qn('a:solidFill')}")
    if fill is None:
        return
    for child in list(fill):
        fill.remove(child)
    color_el = etree.SubElement(fill, qn("a:srgbClr"))
    color_el.set("val", color_hex)


def _set_dpt_colors(ser, n_points, highlight_idx):
    """Recolore les points du graphique (c:dPt) : `highlight_idx` en
    HIGHLIGHT_COLOR, tous les autres en OTHER_COLOR, et retire les points
    au-delà de `n_points` (édition avec moins de RANKING_WINDOW_SIZE
    participants pour ce canal).

    Un point sans c:dPt dans le modèle (ex. le modèle d'origine n'avait que
    7 séries d'exemple pour un graphique qui en affiche maintenant 8)
    garde par défaut la couleur de base de la série — pas forcément
    OTHER_COLOR (confirmé : une barre se retrouvait bleue par défaut, sans
    qu'aucun code ne l'ait explicitement coloriée). On crée donc les c:dPt
    manquants en clonant un c:dPt existant, plutôt que de laisser un point
    sans couleur explicite."""
    existing = {}
    last_dpt = None
    for dpt in list(ser.findall(qn("c:dPt"))):
        idx_el = dpt.find(qn("c:idx"))
        if idx_el is None:
            continue
        idx = int(idx_el.get("val"))
        if idx >= n_points:
            ser.remove(dpt)
            continue
        existing[idx] = dpt
        last_dpt = dpt

    template_dpt = next(iter(existing.values()), None)
    anchor = last_dpt

    for idx in range(n_points):
        color = HIGHLIGHT_COLOR if idx == highlight_idx else OTHER_COLOR
        if idx in existing:
            dpt = existing[idx]
        elif template_dpt is not None:
            dpt = deepcopy(template_dpt)
            dpt.find(qn("c:idx")).set("val", str(idx))
            order_el = dpt.find(qn("c:order"))
            if order_el is not None:
                order_el.set("val", str(idx))
            if anchor is not None:
                anchor.addnext(dpt)
            else:
                # aucun c:dPt existant du tout : insérer avant c:dLbls/c:cat
                # pour respecter l'ordre imposé par le schéma du c:ser
                before = ser.find(qn("c:dLbls"))
                if before is None:
                    before = ser.find(qn("c:cat"))
                if before is not None:
                    before.addprevious(dpt)
                else:
                    ser.append(dpt)
            anchor = dpt
        else:
            continue
        _recolor_dpt(dpt, color)


# --------------------------------------------------- Graphique de comparaison

def apply_comparison_charts(prs, values):
    """values : dict retourné par build_participant_placeholders (voir
    app/reports/report_data.py) — mêmes balises que le rapport d'étude,
    réutilisées telles quelles ici."""
    for scope, slide_idx in COMPARISON_SLIDE_BY_SCOPE.items():
        if slide_idx >= len(prs.slides):
            continue
        slide = prs.slides[slide_idx]
        chartspace, _, _, numcache = _find_chart_ser_by_marker(slide, "Catégorie")
        if numcache is None:
            continue

        if scope == "global":
            own = _as_float(values.get("Note consolidée"))
            categorie = _as_float(values.get("Global note categorie"))
            tous = _as_float(values.get("Global note tous"))
            laureats = _as_float(values.get("Global note laureats"))
        else:
            own = _as_float(values.get(f"Note sur 20 canal {scope}"))
            categorie = _as_float(values.get(f"Total {scope} note categorie"))
            tous = _as_float(values.get(f"{scope} note tous"))
            laureats = _as_float(values.get(f"{scope} note laureats"))

        display_values = (own, categorie, tous, laureats)
        _set_num_cache(numcache, [v if v is not None else 0.0 for v in display_values])
        _set_value_axis_range(chartspace, display_values)


# ------------------------------------------------------ Graphique de classement

RANKING_HARD_CAP = 20


def _ranking_window(ranking, participant_id, size=RANKING_WINDOW_SIZE, hard_cap=RANKING_HARD_CAP):
    """Fenêtre de `ranking` (déjà trié décroissant) SANS TROU entre le rang 1
    et le participant : si celui-ci est déjà dans le top `size`, fenêtre
    simple ranking[:size] (son propre cas). Sinon, la fenêtre s'ÉTEND du
    rang 1 jusqu'à lui (donc parfois plus de `size` barres), plutôt que de
    risquer d'exclure un concurrent mieux classé que lui : un simple
    centrage, ou même la seule réservation du rang 1, avaient déjà chacun
    laissé disparaître un concurrent mieux classé du graphique (confirmé 2
    fois sur le canal Internet). Repli sur un centrage classique seulement
    si le participant est classé au-delà de `hard_cap` (édition avec
    beaucoup de participants testés sur ce canal) : la référence au rang 1
    n'est alors plus garantie, mais generateur un graphique de `hard_cap`+
    barres serait illisible."""
    n = len(ranking)
    pos = next((i for i, r in enumerate(ranking) if r["participant_id"] == participant_id), None)
    if pos is None or n == 0:
        return [], None

    if pos < size:
        window_size = min(size, n)
        return ranking[:window_size], pos

    extended_size = min(pos + 1, hard_cap, n)
    if extended_size > pos:
        return ranking[:extended_size], pos

    window_size = min(size, n)
    half = window_size // 2
    start = max(0, min(pos - half, n - window_size))
    window = ranking[start:start + window_size]
    return window, pos - start


def _force_horizontal_category_labels(chartspace):
    """Sans réglage explicite, PowerPoint choisit lui-même l'orientation ET
    l'espacement des étiquettes de l'axe des catégories selon la largeur
    disponible par barre — confirmé : un graphique dupliqué tel quel d'un
    canal à cadre large (Téléphone) vers un cadre plus étroit (Chat)
    affichait les mêmes étiquettes en diagonale, PUIS une fois l'angle
    corrigé, une sur deux (Participant 1, Participant 3, ... l'axe saute
    l'intervalle qu'il juge nécessaire pour ne pas les faire se chevaucher).
    On force donc l'orientation ET l'affichage de CHAQUE étiquette, comme
    déjà réglé en dur sur les graphiques de comparaison du modèle
    (rot="0" vert="horz")."""
    catax = chartspace.find(f".//{qn('c:catAx')}")
    if catax is None:
        return
    txpr = catax.find(qn("c:txPr"))
    if txpr is None:
        txpr = etree.SubElement(catax, qn("c:txPr"))
    bodypr = txpr.find(qn("a:bodyPr"))
    if bodypr is None:
        bodypr = etree.Element(qn("a:bodyPr"))
        txpr.insert(0, bodypr)
    bodypr.set("rot", "0")
    bodypr.set("vert", "horz")

    # c:tickLblSkip (intervalle entre 2 étiquettes affichées) doit être
    # placé juste avant c:noMultiLvlLbl (ordre imposé par le schéma du
    # c:catAx) ; absent du modèle, PowerPoint choisit alors lui-même
    # l'intervalle selon la largeur disponible.
    if catax.find(qn("c:tickLblSkip")) is None:
        skip_el = etree.Element(qn("c:tickLblSkip"))
        skip_el.set("val", "1")
        anchor = catax.find(qn("c:noMultiLvlLbl"))
        if anchor is not None:
            anchor.addprevious(skip_el)
        else:
            catax.append(skip_el)
    else:
        catax.find(qn("c:tickLblSkip")).set("val", "1")


def apply_ranking_charts(prs, participant, cache):
    ranking_by_scope = cache.get("ranking", {})
    for scope, slide_idx in COMPARISON_SLIDE_BY_SCOPE.items():
        if slide_idx >= len(prs.slides):
            continue
        slide = prs.slides[slide_idx]
        chartspace, ser, strcache, numcache = _find_chart_ser_by_marker(slide, "Participant")
        if ser is None:
            continue  # pas de graphique de classement pour ce canal (ex. chat)

        window, own_idx = _ranking_window(ranking_by_scope.get(scope, []), participant.id)
        if not window:
            continue

        labels = [
            participant.participant_name if i == own_idx else f"Participant {i + 1}"
            for i in range(len(window))
        ]
        scores = [w["score"] for w in window]
        _set_str_cache(strcache, labels)
        _set_num_cache(numcache, scores)
        _set_dpt_colors(ser, len(window), own_idx)
        _set_value_axis_range(chartspace, scores)
        _force_horizontal_category_labels(chartspace)


def _ordinal_fr(n):
    return f"{n}er" if n == 1 else f"{n}ème"


def apply_classement_text(prs, participant, cache):
    """Diapositive 5 (globale) : remplace le texte "Classement XXème" par
    le classement réel du participant sur l'ensemble des participants de
    l'édition (note consolidée)."""
    slide_idx = COMPARISON_SLIDE_BY_SCOPE["global"]
    if slide_idx >= len(prs.slides):
        return
    slide = prs.slides[slide_idx]
    ranking = cache.get("ranking", {}).get("global", [])
    pos = next((i for i, r in enumerate(ranking) if r["participant_id"] == participant.id), None)
    if pos is None:
        return

    for shape in slide.shapes:
        if not getattr(shape, "has_text_frame", False):
            continue
        cnv_pr = shape._element.find(f".//{qn('p:cNvPr')}")
        if cnv_pr is not None and cnv_pr.get("hidden") == "1":
            continue  # formes de brouillon invisibles (ex. "Classement / <4"), pas le vrai texte
        if "Classement XX" not in shape.text_frame.text:
            continue
        paragraph = shape.text_frame.paragraphs[0]
        if not paragraph.runs:
            continue
        paragraph.runs[0].text = f"Classement {_ordinal_fr(pos + 1)} "
        for run in paragraph.runs[1:]:
            run.text = ""
        break


# --------------------------------------------------- Répartition des critères

CRITERION_LINE_RE = re.compile(r"^C(\d+)\s+(.+)$")

# Couleurs de repli si le modèle n'en code aucune dans ses listes (vert / rouge des carrés du modèle).
DEFAULT_GREEN_HEX = "B1CD2B"
DEFAULT_RED_HEX = "FF0000"


def _paragraph_text(paragraph):
    return "".join(run.text for run in paragraph.runs)


def _group_squares(slide):
    """Rectangles ABSOLUS (left, top, width, height) du carré vert (gauche) et du carré rouge (droite) : les 2
    formes libres du groupe de la diapositive, dont les coordonnées sont locales au groupe (échelle chExt/ext)."""
    group = next((s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.GROUP), None)
    if group is None:
        return None, None
    xfrm = group._element.find(".//" + qn("a:xfrm"))
    off, ext = xfrm.find(qn("a:off")), xfrm.find(qn("a:ext"))
    ch_off, ch_ext = xfrm.find(qn("a:chOff")), xfrm.find(qn("a:chExt"))
    sx = int(ext.get("cx")) / int(ch_ext.get("cx"))
    sy = int(ext.get("cy")) / int(ch_ext.get("cy"))
    rects = []
    for child in group.shapes:
        rects.append((
            round(int(off.get("x")) + (child.left - int(ch_off.get("x"))) * sx),
            round(int(off.get("y")) + (child.top - int(ch_off.get("y"))) * sy),
            round(child.width * sx), round(child.height * sy),
        ))
    if len(rects) != 2:
        return None, None
    rects.sort(key=lambda r: r[0])
    return rects[0], rects[1]


def _find_criteria_boxes(slide):
    """Les 2 listes de critères (vert à gauche / rouge à droite) : les formes automatiques dont TOUS les
    paragraphes non vides sont de la forme « C<n> <nom> », ou dont le seul contenu est « - » (liste vide dans le
    modèle, ex. Internet). Repérées par leur contenu plutôt que par leur position, puisque les modèles de
    restitution changent de mise en page."""
    candidates = []
    for s in slide.shapes:
        if s.shape_type != MSO_SHAPE_TYPE.AUTO_SHAPE or not getattr(s, "has_text_frame", False):
            continue
        paragraphs = [p for p in s.text_frame.paragraphs if _paragraph_text(p).strip()]
        if not paragraphs:
            continue
        if all(CRITERION_LINE_RE.match(_paragraph_text(p).strip()) for p in paragraphs) or s.text_frame.text.strip() == "-":
            candidates.append(s)
    if len(candidates) != 2:
        return None, None
    candidates.sort(key=lambda s: s.left)
    return candidates[0], candidates[1]


def _box_items(shape):
    """[(code, nom)] des lignes « C<n> <nom> » d'une liste, dans l'ordre du modèle."""
    items = []
    for p in shape.text_frame.paragraphs:
        m = CRITERION_LINE_RE.match(_paragraph_text(p).strip())
        if m:
            items.append((int(m.group(1)), m.group(2).strip()))
    return items


def _first_criterion_paragraph(shape):
    return next((p for p in shape.text_frame.paragraphs if CRITERION_LINE_RE.match(_paragraph_text(p).strip())), None)


def _box_color_hex(shape, fallback):
    """Couleur (hex) du texte de la liste, lue dans son premier paragraphe : celle que le modèle y a réglée."""
    for p in shape.text_frame.paragraphs:
        for run_el in p._p.findall(qn("a:r")):
            clr = run_el.find(f"{qn('a:rPr')}/{qn('a:solidFill')}/{qn('a:srgbClr')}")
            if clr is not None:
                return clr.get("val")
    return fallback


def _set_paragraph_color(paragraph_el, color_hex):
    for run_el in paragraph_el.findall(qn("a:r")):
        rpr = run_el.find(qn("a:rPr"))
        if rpr is None:
            continue
        fill = rpr.find(qn("a:solidFill"))
        if fill is not None:
            rpr.remove(fill)
        fill = etree.SubElement(rpr, qn("a:solidFill"))
        etree.SubElement(fill, qn("a:srgbClr")).set("val", color_hex)
        rpr.insert(0, fill)  # a:solidFill doit précéder a:latin dans a:rPr


def _rebuild_criteria_list(shape, items, template_p_el, color_hex):
    """items : liste de (code, nom). Reconstruit les paragraphes de la forme en clonant un paragraphe modèle
    (2 runs : code en gras + nom), recolorié dans la couleur de la liste. Liste vide : un seul « - » (comme le
    modèle d'origine)."""
    txbody = shape.text_frame._txBody
    for p in list(shape.text_frame.paragraphs):
        txbody.remove(p._p)
    if not items:
        new_el = deepcopy(template_p_el)
        runs = new_el.findall(qn("a:r"))
        if len(runs) >= 2:
            new_el.remove(runs[0])
            runs = runs[1:]
        runs[0].find(qn("a:t")).text = "-"
        _set_paragraph_color(new_el, color_hex)
        txbody.append(new_el)
        return
    for code, name in items:
        new_el = deepcopy(template_p_el)
        runs = new_el.findall(qn("a:r"))
        runs[0].find(qn("a:t")).text = f"C{code} "
        runs[1].find(qn("a:t")).text = name
        for extra in runs[2:]:
            new_el.remove(extra)
        _set_paragraph_color(new_el, color_hex)
        txbody.append(new_el)


def _place_box(shape, square, n_lines, line_height):
    """Centre la liste dans son carré (largeur du carré, hauteur = nb de lignes x interligne)."""
    left, top, width, height = square
    shape.width = width
    shape.left = left
    shape.height = max(1, n_lines) * line_height
    shape.top = round(top + (height - shape.height) / 2)


def apply_criteria_split(prs, channel, values):
    """values : dict de build_participant_placeholders. Répartit les critères listés dans le modèle (les lignes
    « C<n> <nom> » des 2 listes) entre le carré vert et le carré rouge, d'après la note du participant sur ce
    critère comparée à la note moyenne du critère pour TOUS les participants de l'édition (tests QS = Completed,
    comme les colonnes « vous » et « tous » du rapport) :
    - note du participant >= moyenne de tous (arrondies à 2 décimales, comme affichées) -> vert, liste de gauche ;
    - sinon -> rouge, liste de droite.
    Un critère sans note exploitable (« Non observable » partout) pour le participant, ou sans moyenne, n'est
    placé dans aucun des deux carrés."""
    slide_idx = CRITERIA_SLIDE_BY_CHANNEL.get(channel)
    if slide_idx is None or slide_idx >= len(prs.slides):
        return
    slide = prs.slides[slide_idx]
    green_box, red_box = _find_criteria_boxes(slide)
    green_sq, red_sq = _group_squares(slide)
    if green_box is None or red_box is None or green_sq is None:
        return

    # liste de départ = tous les critères présents dans le modèle, dans l'ordre du récapitulatif des critères du canal
    master = dict(_box_items(green_box) + _box_items(red_box))
    order = {code: i for i, code in enumerate(CRITERIA_BY_CHANNEL[channel])}
    codes = sorted(master, key=lambda c: order.get(c, 99))

    template_p = _first_criterion_paragraph(green_box) or _first_criterion_paragraph(red_box)
    if template_p is None:
        return
    green_hex = _box_color_hex(green_box, DEFAULT_GREEN_HEX)
    red_hex = _box_color_hex(red_box, DEFAULT_RED_HEX)
    reference = green_box if len(green_box.text_frame.paragraphs) >= len(red_box.text_frame.paragraphs) else red_box
    line_height = round(reference.height / max(1, len(reference.text_frame.paragraphs)))
    template_el = deepcopy(template_p._p)

    green_items, red_items = [], []
    for code in codes:
        vous = _as_float(values.get(f"C{code} {channel} note vous"))
        tous = _as_float(values.get(f"C{code} {channel} note tous"))
        if vous is None or tous is None:
            continue
        (green_items if round(vous, 2) >= round(tous, 2) else red_items).append((code, master[code]))

    _rebuild_criteria_list(green_box, green_items, template_el, green_hex)
    _rebuild_criteria_list(red_box, red_items, template_el, red_hex)
    _place_box(green_box, green_sq, len(green_items), line_height)
    _place_box(red_box, red_sq, len(red_items), line_height)


# ---------------------------------------------------------------- Point d'entrée

def apply_debrief_visuals(prs, participant, cache, values):
    """Point d'entrée unique, appelé après substitution des balises texte
    (voir app/restitutions/routes.py::create_restitution) : graphiques de
    comparaison/classement + classement texte + répartition des critères.
    Best-effort par élément : un élément dont les formes ne correspondent
    pas à la structure attendue est simplement ignoré, pour ne jamais faire
    échouer toute la génération à cause d'un seul graphique."""
    try:
        apply_comparison_charts(prs, values)
    except Exception:
        pass
    try:
        apply_ranking_charts(prs, participant, cache)
    except Exception:
        pass
    try:
        apply_classement_text(prs, participant, cache)
    except Exception:
        pass
    for channel in CHANNEL_ORDER:
        try:
            apply_criteria_split(prs, channel, values)
        except Exception:
            continue
