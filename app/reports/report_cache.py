"""
Cache des agrégats d'édition utilisés par le rapport d'étude (portées
"tous"/"categorie"/"laureats"/"non_laureats" — voir report_data.py).

Sans ce cache, générer un rapport rechargeait et retraitait TOUS les tests
de l'édition à chaque fois, ce qui faisait dépasser la mémoire disponible
sur Render dès que l'édition grossissait un peu (et empirait à chaque
rapport enchaîné). Le calcul lourd (compute_edition_cache) n'a lieu qu'une
fois, quand l'utilisateur relance « Liste des lauréats » — geste déjà
obligatoire avant de générer des rapports d'étude.

`get_fresh_edition_cache` compare une signature bon marché (nombre de
tests de l'édition + date du plus récent chargement) à celle enregistrée
avec le cache : si les résultats ont changé depuis, le cache est considéré
périmé (None) et l'appelant doit demander à l'utilisateur de relancer
« Liste des lauréats » avant de générer un rapport.
"""

from datetime import datetime

from sqlalchemy import func

from app.extensions import db
from app.models import EditionReportCache, Participant, TestResult
from app.reports.report_data import compute_scope_values, _avg
from app.results.scoring import (
    build_compilation_rows,
    build_category_winners,
    compute_importance,
    compute_test_score,
    CRITERIA_BY_CHANNEL,
)
from app.results.presentation import CHANNEL_ORDER


def _results_signature(edition_id):
    count = TestResult.query.filter_by(edition_id=edition_id).count()
    latest = db.session.query(func.max(TestResult.uploaded_at)).filter_by(edition_id=edition_id).scalar()
    return f"{count}:{latest.isoformat() if latest else ''}"


def get_fresh_edition_cache(edition_id):
    """Retourne le dict de données mis en cache s'il correspond encore aux
    résultats actuels de l'édition, sinon None (périmé ou jamais calculé)."""
    entry = EditionReportCache.query.filter_by(edition_id=edition_id).first()
    if entry is None or entry.results_signature != _results_signature(edition_id):
        return None
    return entry.data


def _channel_tests_with_note(channel, all_tests):
    result = []
    for t in all_tests:
        if t.channel != channel:
            continue
        score = compute_test_score(channel, t.raw_data or {})
        if score is not None:
            result.append((t.raw_data or {}, score["note_20"]))
    return result


def compute_edition_cache(edition_id):
    """Calcule (une seule fois, coûteux) tous les agrégats d'édition dont a
    besoin la génération de rapports d'étude. Ne conserve QUE ces agrégats
    (pas les tests bruts) : la taille du cache ne dépend que du nombre de
    critères/canaux/catégories, pas du nombre de participants ou de tests."""
    all_participants = Participant.query.filter_by(edition_id=edition_id).all()
    all_tests = TestResult.query.filter_by(edition_id=edition_id).all()

    rows = build_compilation_rows(all_participants, all_tests)
    row_by_pid = {r["participant_id"]: r for r in rows}
    winners = build_category_winners(rows)
    laureat_ids = {w["winner_participant_id"] for w in winners}
    tested_ids = {r["participant_id"] for r in rows if r["nb_tests_total"] > 0}
    non_laureat_ids = tested_ids - laureat_ids

    tests_by_participant = {}
    for t in all_tests:
        if t.participant_id:
            tests_by_participant.setdefault(t.participant_id, []).append(t)

    def tests_for(participant_ids):
        result = []
        for pid in participant_ids:
            result.extend(tests_by_participant.get(pid, []))
        return result

    def avg_consolidated(participant_ids):
        scores = [
            row_by_pid[pid]["consolidated_score"]
            for pid in participant_ids
            if pid in row_by_pid and row_by_pid[pid]["consolidated_score"] is not None
        ]
        avg = _avg(scores)
        return "—" if avg is None else f"{avg:.2f}".replace(".", ",")

    by_category = {}
    global_note_by_category = {}
    category_ids = {p.category_id for p in all_participants if p.category_id is not None}
    for category_id in category_ids:
        member_ids = {p.id for p in all_participants if p.category_id == category_id}
        by_category[str(category_id)] = compute_scope_values(tests_for(member_ids))
        global_note_by_category[str(category_id)] = avg_consolidated(member_ids)

    # Importance (coefficient de Pearson au carré) par critère, sur
    # l'ensemble des tests de l'édition pour ce canal — indépendant du
    # participant, utilisé par le mapping d'importance (report_visuals.py).
    importance = {}
    for channel in CHANNEL_ORDER:
        tests_with_note = _channel_tests_with_note(channel, all_tests)
        importance[channel] = {}
        for code in CRITERIA_BY_CHANNEL[channel]:
            r = compute_importance(channel, code, tests_with_note)
            importance[channel][str(code)] = (r ** 2) if r is not None else 0.0

    return {
        "tous": compute_scope_values(tests_for(tested_ids)),
        "laureats": compute_scope_values(tests_for(laureat_ids)),
        "non_laureats": compute_scope_values(tests_for(non_laureat_ids)),
        "by_category": by_category,
        "empty_scope": compute_scope_values([]),
        "global_note": {
            "tous": avg_consolidated(tested_ids),
            "laureats": avg_consolidated(laureat_ids),
            "non_laureats": avg_consolidated(non_laureat_ids),
            "by_category": global_note_by_category,
        },
        "importance": importance,
        "has_winners": bool(winners),
    }


def refresh_edition_cache(edition_id, user_id=None):
    """Calcule et enregistre le cache — appelé quand l'utilisateur relance
    « Liste des lauréats » (voir results/routes.py::winners_page)."""
    data = compute_edition_cache(edition_id)
    signature = _results_signature(edition_id)

    entry = EditionReportCache.query.filter_by(edition_id=edition_id).first()
    if entry is None:
        entry = EditionReportCache(edition_id=edition_id)
        db.session.add(entry)
    entry.data = data
    entry.results_signature = signature
    entry.computed_by_id = user_id
    entry.computed_at = datetime.utcnow()
    db.session.commit()
    return data
