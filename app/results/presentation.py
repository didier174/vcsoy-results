"""
Fonctions de préparation des données de test (TestResult.raw_data) pour
leur présentation : extraction des colonnes « Code N » avec leur
observation associée, et des « autres données » restantes.

Important : la signification d'un « Code N » dépend du canal (l'onglet
d'origine) — Code 3 en téléphone n'a rien à voir avec Code 3 en chat.
On ne mélange donc jamais des tests de canaux différents dans un même
tableau à colonnes partagées ; chaque test affiche uniquement ses propres
codes, clairement associés à son canal.
"""

import re

CODE_VALUE_RE = re.compile(r"^code\s*(\d+)$", re.IGNORECASE)
CODE_ANY_RE = re.compile(r"^code\s*\d+(\s*obs)?$", re.IGNORECASE)

CHANNEL_LABELS = {
    "phone": "Téléphone",
    "mail": "Mail",
    "web": "WEB",
    "rs": "RS",
    "chat": "Chat",
}
CHANNEL_ORDER = ["phone", "mail", "web", "rs", "chat"]

# Colonne contenant la date du test, selon le canal (le nom de la colonne
# de date n'est pas le même sur l'onglet Phone que sur les autres).
DATE_FIELD_BY_CHANNEL = {
    "phone": "Call_Date",
    "mail": "Day_Open",
    "web": "Day_Open",
    "rs": "Day_Open",
    "chat": "Day_Open",
}


def _compact(header):
    return re.sub(r"\s+", "", str(header).strip().lower())


def extract_codes(raw_data):
    """Retourne [{number, header, value, observation}, ...] triés par numéro."""
    if not raw_data:
        return []

    compact_index = {_compact(h): h for h in raw_data.keys()}

    codes = []
    seen = set()
    for header in raw_data.keys():
        m = CODE_VALUE_RE.match(str(header).strip())
        if not m:
            continue
        num = int(m.group(1))
        if num in seen:
            continue
        seen.add(num)

        obs_header = compact_index.get(f"code{num}obs")
        codes.append({
            "number": num,
            "header": header,
            "value": raw_data.get(header),
            "observation": raw_data.get(obs_header) if obs_header else None,
        })

    codes.sort(key=lambda c: c["number"])
    return codes


def extract_other_fields(raw_data, exclude_headers=None):
    """Retourne les champs qui ne sont ni Code N, ni Code N obs, ni explicitement exclus."""
    if not raw_data:
        return {}
    exclude_headers = exclude_headers or set()
    other = {}
    for header, value in raw_data.items():
        if header in exclude_headers:
            continue
        if CODE_ANY_RE.match(str(header).strip()):
            continue
        other[header] = value
    return other


def build_test_view(test_result):
    """Construit une vue complète et JSON-sérialisable d'un TestResult."""
    channel = test_result.channel
    date_field = DATE_FIELD_BY_CHANNEL.get(channel)
    raw_data = test_result.raw_data or {}
    date_value = raw_data.get(date_field) if date_field else None

    exclude = {date_field} if date_field else set()
    codes = extract_codes(raw_data)
    other_fields = extract_other_fields(raw_data, exclude_headers=exclude)

    return {
        "id": test_result.id,
        "test_id": test_result.test_id,
        "channel": channel,
        "channel_label": CHANNEL_LABELS.get(channel, channel),
        "date": date_value,
        "category_label": test_result.category.label() if test_result.category else "(catégorie supprimée)",
        "participant_name": test_result.participant.participant_name if test_result.participant else "(participant supprimé)",
        "participant_code": test_result.participant.code if test_result.participant else "",
        "codes": codes,
        "other_fields": other_fields,
        "record_id": test_result.record.id if test_result.record else None,
    }
