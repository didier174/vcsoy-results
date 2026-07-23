"""
Met à jour les 2 graphiques natifs PowerPoint du modèle de rapport
d'étude, qui ne sont pas de simples balises {{ ... }} texte :

- diapositive 9 : jauge (barre empilée à 100%) note globale + note par
  canal, pour le participant, avec un rond de couleur positionné au bout
  de chaque barre et un texte "Canal non testé" pour un canal absent.
- diapositives 14/18/22/26/30 : mapping d'importance (nuage de points),
  un point par critère du canal — abscisse = taux de conformité de
  l'entreprise sur ce critère, ordonnée = importance de ce critère dans
  la note globale du canal (calculée sur l'ensemble de l'édition) — avec
  un calibrage des axes (min/max/croisement) adapté aux valeurs du
  participant, pour rester lisible comme dans le modèle.

Les balises {{ ... }} de generator.py ne s'appliquent qu'au texte : ces
graphiques nécessitent de modifier directement le cache de données XML
du graphique (repris tel quel par PowerPoint/LibreOffice à l'ouverture),
tout en conservant sa mise en forme (étiquettes, couleurs, position
manuelle des étiquettes, traits de rappel) déjà réglée dans le modèle.
"""

import copy
import statistics

from lxml import etree
from pptx.oxml.ns import qn

from app.models import Participant, TestResult
from app.results.presentation import CHANNEL_ORDER
from app.results.scoring import (
    build_compilation_rows,
    compute_test_score,
    compute_importance,
    compute_criterion_stats,
)


# ------------------------------------------------------- Diapositive 9 : jauge

GAUGE_ROW_ORDER = ["global", "phone", "mail", "web", "rs", "chat"]
GAUGE_UNTESTED_TEXT_SHAPES = {"mail": "ZoneTexteMail", "rs": "ZoneTexteRes"}
GAUGE_OVAL_NAME_PREFIX = "Slide11_OvalNote"

# Position horizontale (EMU) d'un rond en fonction de la note sur 20 :
# régression linéaire sur les 6 ronds et leurs valeurs d'exemple dans le
# modèle d'origine (résidus < 50 000 EMU, soit < 1,5 mm — un très bon
# ajustement, qui confirme un positionnement proportionnel à la note sur
# toute la largeur de la jauge).
GAUGE_OVAL_X_SLOPE = 218753.91863099797
GAUGE_OVAL_X_INTERCEPT = 2824825.1388052916


def _gauge_oval_left(note_20):
    return round(GAUGE_OVAL_X_SLOPE * note_20 + GAUGE_OVAL_X_INTERCEPT)


def _set_hidden(shape, hidden):
    cnv_pr = shape._element.find(f".//{qn('p:cNvPr')}")
    if cnv_pr is None:
        return
    if hidden:
        cnv_pr.set("hidden", "1")
    elif "hidden" in cnv_pr.attrib:
        del cnv_pr.attrib["hidden"]


def _clone_untested_label(template_shape, target_top, new_id):
    new_el = copy.deepcopy(template_shape._element)
    cnv_pr = new_el.find(f".//{qn('p:cNvPr')}")
    cnv_pr.set("id", str(new_id))
    if "hidden" in cnv_pr.attrib:
        del cnv_pr.attrib["hidden"]
    off = new_el.find(f".//{qn('a:xfrm')}/{qn('a:off')}")
    off.set("y", str(target_top))
    return new_el


def apply_gauge_chart(prs, participant, edition_id, rows=None):
    slide = prs.slides[8]  # diapositive 9
    chart_shape = next((s for s in slide.shapes if s.name == "Graph_Bar"), None)
    if chart_shape is None or not chart_shape.has_chart:
        return

    if rows is None:
        all_participants = Participant.query.filter_by(edition_id=edition_id).all()
        all_tests = TestResult.query.filter_by(edition_id=edition_id).all()
        rows = build_compilation_rows(all_participants, all_tests)
    own_row = next((r for r in rows if r["participant_id"] == participant.id), None)

    channel_flags = {
        "phone": participant.channel_phone, "mail": participant.channel_mail,
        "web": participant.channel_web, "rs": participant.channel_rs, "chat": participant.channel_chat,
    }

    notes = {}
    for key in GAUGE_ROW_ORDER:
        if key == "global":
            notes[key] = own_row["consolidated_score"] if own_row else None
        elif channel_flags.get(key):
            notes[key] = own_row["channels"][key]["note_20"] if own_row else None
        else:
            notes[key] = None

    series1 = [notes[key] if notes[key] is not None else 0.0 for key in GAUGE_ROW_ORDER]
    series2 = [max(0.0, 20.0 - v) for v in series1]

    all_ser = chart_shape.chart._chartSpace.findall(f".//{qn('c:ser')}")
    for ser_el, new_values in zip(all_ser, [series1, series2]):
        val_el = ser_el.find(qn("c:val"))
        numref = val_el.find(qn("c:numRef")) if val_el is not None else None
        numlit = val_el.find(qn("c:numLit")) if val_el is not None else None
        target = numlit if numlit is not None else (numref.find(qn("c:numCache")) if numref is not None else None)
        if target is not None:
            _set_numlit_points(target, {i: v for i, v in enumerate(new_values)})

    # Ronds de couleur : un par ligne (global/phone/mail/web/rs/chat), triés
    # par position verticale dans le modèle (2 d'entre eux partagent le même
    # nom "Slide11_OvalNoteReseau" par erreur de conception du modèle — on
    # se base donc sur l'ordre vertical, fiable, plutôt que sur le nom).
    ovals = sorted(
        (s for s in slide.shapes if s.name.startswith(GAUGE_OVAL_NAME_PREFIX)),
        key=lambda s: s.top,
    )
    for key, oval in zip(GAUGE_ROW_ORDER, ovals):
        note = notes[key]
        if note is None:
            _set_hidden(oval, True)
        else:
            _set_hidden(oval, False)
            oval.left = _gauge_oval_left(note)

    # "Canal non testé" à la place de la note : 2 zones de texte existent déjà
    # dans le modèle (Mail/RS, masquées par défaut) ; on les clone pour les 3
    # canaux qui n'en ont pas (Phone/Web/Chat), positionnées sur la même ligne
    # que leur rond (désormais masqué).
    label_template = next((s for s in slide.shapes if s.name == "ZoneTexteMail"), None)
    max_id = max((s.shape_id for s in slide.shapes), default=0)
    oval_by_row = dict(zip(GAUGE_ROW_ORDER, ovals))
    for channel in ("phone", "mail", "web", "rs", "chat"):
        tested = notes[channel] is not None
        shape_name = GAUGE_UNTESTED_TEXT_SHAPES.get(channel)
        if shape_name:
            shape = next((s for s in slide.shapes if s.name == shape_name), None)
            if shape is not None:
                _set_hidden(shape, tested)
        elif not tested and label_template is not None:
            oval = oval_by_row.get(channel)
            if oval is not None:
                target_top = oval.top + oval.height // 2 - label_template.height // 2
                max_id += 1
                new_el = _clone_untested_label(label_template, target_top, max_id)
                slide.shapes._spTree.append(new_el)


def _set_numlit_points(numlit_el, values_by_idx):
    for pt in list(numlit_el.findall(qn("c:pt"))):
        numlit_el.remove(pt)
    ptcount = numlit_el.find(qn("c:ptCount"))
    if ptcount is not None:
        ptcount.set("val", str(len(values_by_idx)))
    for idx in sorted(values_by_idx):
        pt = etree.SubElement(numlit_el, qn("c:pt"))
        pt.set("idx", str(idx))
        v = etree.SubElement(pt, qn("c:v"))
        v.text = repr(float(values_by_idx[idx]))


# --------------------------------------- Diapositives 14/18/22/26/30 : mapping

# idx (position du point dans le graphique, 0-based) -> code du critère
# "Code N" — déduit des étiquettes déjà présentes dans le modèle pour
# chaque canal (voir historique de la conversation). Le critère
# "Impression générale" est systématiquement absent du mapping sur les 5
# canaux (choix déjà fait dans le modèle d'origine, pas une balise à
# renseigner).
MAPPING_SLIDE_BY_CHANNEL = {"phone": 13, "mail": 17, "web": 21, "rs": 25, "chat": 29}  # 0-based
MAPPING_POINT_CODE = {
    "phone": {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8, 8: 9, 9: 10, 10: 11, 11: 12, 12: 13, 13: 15},
    "mail": {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8, 8: 9, 9: 11, 10: 10, 11: 13, 12: 14},
    "web": {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8, 8: 9, 9: 10, 10: 11, 11: 13},
    "rs": {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8, 8: 9, 9: 10, 10: 11, 11: 12, 12: 14, 13: 15},
    "chat": {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8, 8: 9, 9: 10, 10: 11, 11: 12, 12: 14},
}

# Marge (dans l'unité des données, 0-1 pour l'abscisse comme pour
# l'ordonnée) ajoutée de part et d'autre de la plage réelle des points pour
# calibrer les axes : déduite du modèle d'origine (mêmes échelles 0-1), où
# elle vaut ~0,3 des deux côtés. Le point de croisement des axes (souvent
# hors-centre dans le modèle) correspond, une fois vérifié, à la médiane des
# valeurs de l'AUTRE axe — ce qui place la ligne de croisement au milieu du
# nuage de points plutôt qu'à une valeur arbitraire comme 0.
MAPPING_AXIS_PADDING = 0.3


def _channel_tests_with_note(channel, all_tests):
    result = []
    for t in all_tests:
        if t.channel != channel:
            continue
        score = compute_test_score(channel, t.raw_data or {})
        if score is not None:
            result.append((t.raw_data or {}, score["note_20"]))
    return result


def _criterion_pct_vous(channel, code, vous_tests):
    """% de scores "Bon" (valeur brute = 2) du participant pour ce
    critère — même définition confirmée que pour les tableaux détaillés."""
    stats = compute_criterion_stats(channel, code, [t.raw_data for t in vous_tests])
    return (stats["pct"] or 0) / 100.0


def _scatter_axes(chartspace):
    """Retourne (axe_x, axe_y) : les 2 éléments <c:valAx> d'un graphique
    XY, identifiés via l'ordre de leurs <c:axId> dans <c:scatterChart>
    (confirmé, cet ordre est bien [abscisse, ordonnée]), pas leur ordre
    dans le document (moins fiable)."""
    scatter = chartspace.find(f".//{qn('c:scatterChart')}")
    if scatter is None:
        return None, None
    axid_els = scatter.findall(qn("c:axId"))
    if len(axid_els) < 2:
        return None, None
    x_axid, y_axid = axid_els[0].get("val"), axid_els[1].get("val")
    by_id = {}
    for ax in chartspace.findall(f".//{qn('c:valAx')}"):
        axid_el = ax.find(qn("c:axId"))
        if axid_el is not None:
            by_id[axid_el.get("val")] = ax
    return by_id.get(x_axid), by_id.get(y_axid)


def _set_axis_range(axis_el, data_min, data_max, crosses_at):
    if axis_el is None:
        return
    # c:min/c:max sont dans c:scaling (petit-enfant de c:valAx, pas enfant
    # direct) : recherche en profondeur nécessaire, contrairement à
    # c:crossesAt qui est bien un enfant direct de c:valAx.
    min_el = axis_el.find(f".//{qn('c:min')}")
    max_el = axis_el.find(f".//{qn('c:max')}")
    crosses_el = axis_el.find(qn("c:crossesAt"))
    if min_el is not None:
        min_el.set("val", repr(data_min - MAPPING_AXIS_PADDING))
    if max_el is not None:
        max_el.set("val", repr(data_max + MAPPING_AXIS_PADDING))
    if crosses_el is not None:
        crosses_el.set("val", repr(crosses_at))


def apply_importance_mappings(prs, participant, edition_id, all_tests=None):
    if all_tests is None:
        all_tests = TestResult.query.filter_by(edition_id=edition_id).all()
    vous_tests_by_channel = {
        channel: [t for t in all_tests if t.participant_id == participant.id and t.channel == channel]
        for channel in CHANNEL_ORDER
    }

    for channel in CHANNEL_ORDER:
        slide_idx = MAPPING_SLIDE_BY_CHANNEL[channel]
        slide = prs.slides[slide_idx]
        chart_shape = next(
            (s for s in slide.shapes if getattr(s, "has_chart", False) and s.chart.chart_type == -4169),
            None,
        )
        if chart_shape is None:
            continue

        tests_with_note = _channel_tests_with_note(channel, all_tests)
        point_codes = MAPPING_POINT_CODE[channel]

        # Importance = coefficient de Pearson au carré (toujours positif,
        # reflète l'intensité de la liaison indépendamment du sens), normalisé
        # pour que la somme sur tous les critères du canal fasse 1 — même
        # échelle que les valeurs d'exemple du modèle d'origine.
        raw_importance = {}
        for code in point_codes.values():
            r = compute_importance(channel, code, tests_with_note)
            raw_importance[code] = (r ** 2) if r is not None else 0.0
        total = sum(raw_importance.values())

        x_by_idx, y_by_idx = {}, {}
        vous_tests = vous_tests_by_channel[channel]
        for idx, code in point_codes.items():
            x_by_idx[idx] = _criterion_pct_vous(channel, code, vous_tests)
            y_by_idx[idx] = (raw_importance[code] / total) if total else 0.0

        chart_xml = chart_shape.chart._chartSpace
        ser_el = chart_xml.find(f".//{qn('c:ser')}")
        if ser_el is None:
            continue
        xval_el = ser_el.find(qn("c:xVal"))
        yval_el = ser_el.find(qn("c:yVal"))
        if xval_el is not None:
            numlit = xval_el.find(qn("c:numLit"))
            if numlit is not None:
                _set_numlit_points(numlit, x_by_idx)
        if yval_el is not None:
            numlit = yval_el.find(qn("c:numLit"))
            if numlit is not None:
                _set_numlit_points(numlit, y_by_idx)

        # Calibrage des axes sur la plage réelle des valeurs du participant :
        # sans ça, les axes restent calés sur les valeurs d'exemple du
        # modèle, ce qui peut resserrer/décentrer le nuage de points et faire
        # se chevaucher les étiquettes (déjà positionnées manuellement dans
        # le modèle pour SA plage de valeurs d'origine).
        if x_by_idx and y_by_idx:
            x_axis, y_axis = _scatter_axes(chart_xml)
            xs, ys = list(x_by_idx.values()), list(y_by_idx.values())
            _set_axis_range(x_axis, min(xs), max(xs), statistics.median(ys))
            _set_axis_range(y_axis, min(ys), max(ys), statistics.median(xs))


def apply_report_visuals(prs, participant, edition_id, all_tests=None, rows=None):
    """Point d'entrée unique : applique la jauge (diapo 9) et les 5
    mappings d'importance (diapos 14/18/22/26/30) sur une Presentation déjà
    ouverte (après substitution des balises texte).

    all_tests/rows : déjà calculés par l'appelant (voir reports/routes.py)
    pour éviter de refaire ces requêtes/calculs coûteux (tous les tests de
    l'édition) plusieurs fois dans la même requête HTTP."""
    apply_gauge_chart(prs, participant, edition_id, rows=rows)
    apply_importance_mappings(prs, participant, edition_id, all_tests=all_tests)
