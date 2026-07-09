"""
Validation des fichiers "record" (preuve d'un test mystère) avant
enregistrement, selon les règles définies par l'utilisateur :

- Le nom du fichier doit suivre exactement le format
  "IDMYSTERYTEST-record.ext" (ex. "44031450-record.pdf"), où
  IDMYSTERYTEST est la chaîne de 8 chiffres CCPPXXXX (CC = code
  catégorie, PP = code participant, XXXX = numéro de test).
- CC doit être un code catégorie existant, PP un code participant
  existant dans cette catégorie, et l'ID Mystery Test complet doit
  correspondre à un test déjà chargé (« Chargement fichier résultat »)
  pour l'édition en cours — un record sans test associé est refusé.
- L'extension attendue dépend du canal du test associé : un fichier
  audio pour un test Phone, un PDF pour tous les autres canaux.

Comme pour le chargement des résultats, le chargement des records est
tout-ou-rien : si un seul fichier du lot est invalide, rien n'est
enregistré.
"""

import re

FILENAME_RE = re.compile(r"^(\d{8})-record\.([A-Za-z0-9]+)$", re.IGNORECASE)

AUDIO_EXTENSIONS = {"mp3", "wav", "m4a", "aac", "ogg", "wma", "aiff", "flac"}
PDF_EXTENSIONS = {"pdf"}


def validate_record_files(filenames, categories, participants, tests_by_test_id):
    """
    filenames : liste de noms de fichiers (déjà passés par secure_filename)
    categories : liste des Category de l'édition en cours
    participants : liste des Participant de l'édition en cours
    tests_by_test_id : {test_id: TestResult} pour l'édition en cours

    Retourne (errors, valid) :
    - errors : liste de messages d'erreur (un par fichier invalide)
    - valid : liste de dicts {filename, test_id, test_result, ext}
    """
    category_by_code = {c.code: c for c in categories if c.code}
    participant_by_key = {(p.category_id, p.code): p for p in participants if p.code}

    errors = []
    valid = []

    for filename in filenames:
        m = FILENAME_RE.match(filename)
        if not m:
            errors.append(
                f"« {filename} » : nom de fichier invalide (attendu IDMYSTERYTEST-record.ext, "
                f"ex. 44031450-record.pdf)."
            )
            continue

        test_id, ext = m.group(1), m.group(2).lower()
        cc, pp = test_id[0:2], test_id[2:4]

        category = category_by_code.get(cc)
        if not category:
            errors.append(f"« {filename} » : code catégorie « {cc} » inconnu pour cette édition.")
            continue

        participant = participant_by_key.get((category.id, pp))
        if not participant:
            errors.append(f"« {filename} » : code participant « {pp} » inconnu pour la catégorie « {cc} ».")
            continue

        test = tests_by_test_id.get(test_id)
        if not test:
            errors.append(
                f"« {filename} » : aucun test « {test_id} » trouvé dans les résultats chargés pour cette édition."
            )
            continue

        is_phone = test.channel == "phone"
        if is_phone and ext not in AUDIO_EXTENSIONS:
            errors.append(
                f"« {filename} » : un fichier audio est attendu pour un test Phone (extension « .{ext} » non reconnue)."
            )
            continue
        if not is_phone and ext not in PDF_EXTENSIONS:
            errors.append(
                f"« {filename} » : un fichier PDF est attendu pour ce canal (extension « .{ext} » non reconnue)."
            )
            continue

        valid.append({"filename": filename, "test_id": test_id, "test_result": test, "ext": ext})

    return errors, valid
