"""
Met à jour les 2 graphiques natifs PowerPoint du modèle de rapport
d'étude, qui ne sont pas de simples balises {{ ... }} texte :

- diapositive 9 : jauge (barre empilée à 100%) note globale + note par
  canal, pour le participant.
- diapositives 14/18/22/26/30 : mapping d'importance (nuage de points),
  un point par critère du canal — abscisse = taux de conformité de
  l'entreprise sur ce critère, ordonnée = importance de ce critère dans
  la note globale du canal (calculée sur l'ensemble de l'édition).

Les balises {{ ... }} de generator.py ne s'appliquent qu'au texte : ces
graphiques nécessitent de modifier directement le cache de données XML
du graphique (repris tel quel par PowerPoint/LibreOffice à l'ouverture),
tout en conservant sa mise en forme (étiquettes, couleurs, position
manuelle des étiquettes) déjà réglée dans le modèle.
"""

from lxml import etree

from app.models import Participant, TestResult
from app.results.presentation import CHANNEL_ORDER
from app.results.scoring import (
    build_compilation_rows,
    compute_test_score,
    compute_importance,
    compute_criterion_stats,
)

C_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"


def _qn(tag):
    return f"{{{C_NS}}}{tag}"


# ------------------------------------------------------- Diapositive 9 : jauge

GAUGE_ROW_ORDER = ["global", "phone", "mail", "web", "rs", "chat"]
GAUGE_UNTESTED_TEXT_SHAPES = {"mail": "ZoneTexteMail", "rs": "ZoneTexteRes"}


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

    values = []
    for key in GAUGE_ROW_ORDER:
        if key == "global":
            note = own_row["consolidated_score"] if own_row else None
        elif channel_flags.get(key):
            note = own_row["channels"][key]["note_20"] if own_row else None
        else:
            note = None
        values.append(note if note is not None else 0.0)

    series1 = values
    series2 = [max(0.0, 20.0 - v) for v in values]

    all_ser = chart_shape.chart._chartSpace.findall(f".//{_qn('ser')}")
    for ser_el, new_values in zip(all_ser, [series1, series2]):
        val_el = ser_el.find(_qn("val"))
        numref = val_el.find(_qn("numRef")) if val_el is not None else None
        numlit = val_el.find(_qn("numLit")) if val_el is not None else None
        target = numlit if numlit is not None else (numref.find(_qn("numCache")) if numref is not None else None)
        if target is not None:
            _set_numlit_points(target, {i: v for i, v in enumerate(new_values)})

    # "Canal non testé" : les 2 zones de texte prévues dans le modèle
    for channel, shape_name in GAUGE_UNTESTED_TEXT_SHAPES.items():
        shape = next((s for s in slide.shapes if s.name == shape_name), None)
        if shape is None or not shape.has_text_frame:
            continue
        shape.text_frame.text = "" if channel_flags.get(channel) else "Canal non testé"


def _set_numlit_points(numlit_el, values_by_idx):
    for pt in list(numlit_el.findall(_qn("pt"))):
        numlit_el.remove(pt)
    ptcount = numlit_el.find(_qn("ptCount"))
    if ptcount is not None:
        ptcount.set("val", str(len(values_by_idx)))
    for idx in sorted(values_by_idx):
        pt = etree.SubElement(numlit_el, _qn("pt"))
        pt.set("idx", str(idx))
        v = etree.SubElement(pt, _qn("v"))
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
        ser_el = chart_xml.find(f".//{_qn('ser')}")
        if ser_el is None:
            continue
        xval_el = ser_el.find(_qn("xVal"))
        yval_el = ser_el.find(_qn("yVal"))
        if xval_el is not None:
            numlit = xval_el.find(_qn("numLit"))
            if numlit is not None:
                _set_numlit_points(numlit, x_by_idx)
        if yval_el is not None:
            numlit = yval_el.find(_qn("numLit"))
            if numlit is not None:
                _set_numlit_points(numlit, y_by_idx)


def apply_report_visuals(prs, participant, edition_id, all_tests=None, rows=None):
    """Point d'entrée unique : applique la jauge (diapo 9) et les 5
    mappings d'importance (diapos 14/18/22/26/30) sur une Presentation déjà
    ouverte (après substitution des balises texte).

    all_tests/rows : déjà calculés par l'appelant (voir reports/routes.py)
    pour éviter de refaire ces requêtes/calculs coûteux (tous les tests de
    l'édition) plusieurs fois dans la même requête HTTP."""
    apply_gauge_chart(prs, participant, edition_id, rows=rows)
    apply_importance_mappings(prs, participant, edition_id, all_tests=all_tests)
