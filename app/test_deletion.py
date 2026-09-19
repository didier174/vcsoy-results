"""
Suppression des données rattachées à des tests (TestResult).

Trois tables référencent test_result.id par clé étrangère, sans suppression
en cascade configurée : TestRecord (record d'origine), RedactedRecord (copie
caviardée) et RestitutionTestSelection (sélection de tests de chaque
utilisateur). Supprimer un TestResult sans avoir d'abord supprimé ces lignes
viole la contrainte de clé étrangère et fait planter la requête
(« internal error »).

Le piège ne se voit qu'en production : PostgreSQL applique les clés
étrangères, alors que la base SQLite du développement local ne les vérifie
pas par défaut.
"""

from app.extensions import db
from app.models import TestRecord, RedactedRecord, RestitutionTestSelection


def delete_test_dependents(test_ids):
    """Supprime tout ce qui pointe vers les tests `test_ids` (sans commit).

    À appeler AVANT de supprimer les TestResult correspondants ; le commit
    reste à la charge de l'appelant pour que la suppression soit atomique.
    """
    test_ids = list(test_ids)
    if not test_ids:
        return
    RestitutionTestSelection.query.filter(
        RestitutionTestSelection.test_result_id.in_(test_ids)
    ).delete(synchronize_session=False)
    RedactedRecord.query.filter(RedactedRecord.test_result_id.in_(test_ids)).delete(synchronize_session=False)
    TestRecord.query.filter(TestRecord.test_result_id.in_(test_ids)).delete(synchronize_session=False)
