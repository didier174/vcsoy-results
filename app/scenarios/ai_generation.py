"""
Génération de scénarios par IA (Claude Sonnet 5) pour « Générer un book ».

Le modèle recherche sur le vrai site web du participant (via l'outil
web_search), s'inspire des problématiques de l'étude et des scénarios déjà
validés (few-shot), puis renvoie une liste de nouveaux scénarios sous forme
de JSON.
"""

import json
import re

import anthropic

MODEL = "claude-sonnet-5"

REQUIRED_KEYS = ("type", "contexte", "question", "reponse", "url_source")


class ScenarioGenerationError(Exception):
    """`usage` (dict input_tokens/output_tokens/web_search_count/estimated_cost_usd)
    est rempli dès qu'une réponse a été obtenue avant l'échec, pour pouvoir
    tout de même consigner le coût engagé (voir app/scenarios/routes.py)."""

    def __init__(self, message, usage=None):
        super().__init__(message)
        self.usage = usage or {}


# Tarifs Claude Sonnet 5 (tarif promotionnel en vigueur jusqu'au 2026-08-31 ;
# revient à 3,00 $/15,00 $ ensuite — voir platform.claude.com/docs/en/about-claude/pricing
# et mettre à jour ces constantes à cette date).
INPUT_PRICE_PER_MTOK = 2.00
OUTPUT_PRICE_PER_MTOK = 10.00
WEB_SEARCH_PRICE_PER_1000 = 10.00


def _new_usage_totals():
    return {"input_tokens": 0, "output_tokens": 0, "web_search_count": 0}


def _accumulate_usage(totals, response):
    totals["input_tokens"] += response.usage.input_tokens
    totals["output_tokens"] += response.usage.output_tokens
    if response.usage.server_tool_use:
        totals["web_search_count"] += response.usage.server_tool_use.web_search_requests


def _finalize_usage(totals):
    totals["estimated_cost_usd"] = round(
        totals["input_tokens"] * INPUT_PRICE_PER_MTOK / 1_000_000
        + totals["output_tokens"] * OUTPUT_PRICE_PER_MTOK / 1_000_000
        + totals["web_search_count"] * WEB_SEARCH_PRICE_PER_1000 / 1000,
        4,
    )
    return totals


LANGUAGE_LABELS = {"fr": "français", "en": "anglais"}


def _build_prompt(participant_name, website_url, problematiques_text, examples, num_to_generate, language):
    if examples:
        examples_lines = []
        for ex in examples:
            examples_lines.append(
                f"- Type : {ex['type']}\n"
                f"  Contexte : {ex['contexte']}\n"
                f"  Question : {ex['question']}\n"
                f"  Réponse : {ex['reponse']}"
            )
        examples_text = "\n".join(examples_lines)
    else:
        examples_text = "(aucun scénario validé pour l'instant pour ce participant)"

    language_label = LANGUAGE_LABELS.get(language, "français")

    return f"""Tu prépares des scénarios de client mystère pour une étude de qualité de
service à la clientèle (ESCDA Canada).

Participant : {participant_name}
Site web du participant : {website_url}

Problématiques (points sensibles) à explorer, tirées de la présentation de l'étude :
{problematiques_text or "(aucune problématique fournie)"}

Scénarios déjà validés par l'utilisateur pour ce participant (utilise-les comme
référence de style, de ton et de niveau de détail) :
{examples_text}

Ta tâche : utilise l'outil de recherche web pour explorer le vrai site web du
participant (FAQ, pages d'information générale, conditions, etc.) et trouver de
vraies informations en lien avec les problématiques ci-dessus. À partir de ces
informations, génère {num_to_generate} NOUVEAUX scénarios de client mystère, distincts
des scénarios déjà validés.

IMPORTANT : rédige TOUT le contenu de chaque scénario (contexte, question, réponse)
en {language_label}, y compris si les informations trouvées sur le site sont dans une
autre langue (traduis-les en {language_label}).

Pour chaque scénario :
- "type" : "Prospect" ou "Client" selon la situation
- "contexte" : le contexte qui amène ce prospect/client à contacter le service à la clientèle
- "question" : la question précise que pose le client mystère
- "reponse" : la réponse attendue, basée sur une information réelle trouvée sur le site
- "url_source" : l'URL exacte de la page du site où cette information a été trouvée

Réponds UNIQUEMENT avec un tableau JSON de {num_to_generate} objets ayant exactement
ces clés : type, contexte, question, reponse, url_source. Aucun texte avant ou
après le tableau JSON, aucun bloc de code markdown."""


def _extract_json_array(text):
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Réponse du modèle sans tableau JSON exploitable.")
    return json.loads(text[start : end + 1])


MAX_TOKENS = 16000
MAX_CONTINUATIONS = 3
TOOLS = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 10}]


def _call_claude(client, messages):
    return client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        tools=TOOLS,
        messages=messages,
    )


def generate_scenarios(
    participant_name, website_url, problematiques_text, examples, num_to_generate=10, language="fr"
):
    """
    Retourne (scenarios, usage) : scenarios est une liste de dicts
    {type, contexte, question, reponse, url_source} (longueur <= num_to_generate) ;
    usage un dict {input_tokens, output_tokens, web_search_count, estimated_cost_usd}.
    Lève ScenarioGenerationError (avec exc.usage rempli si une réponse a été
    obtenue avant l'échec) en cas d'échec.

    Appelée depuis un thread d'arrière-plan (voir app/scenarios/routes.py,
    _run_generation) : peut prendre plusieurs minutes sans que cela ne bloque
    de requête web.
    """
    prompt = _build_prompt(participant_name, website_url, problematiques_text, examples, num_to_generate, language)
    user_message = {"role": "user", "content": prompt}
    usage = _new_usage_totals()

    try:
        client = anthropic.Anthropic(timeout=900.0)
        response = _call_claude(client, [user_message])
        _accumulate_usage(usage, response)

        # La recherche web est traitée côté serveur ; si elle atteint sa
        # limite interne d'itérations, l'API renvoie "pause_turn" et il faut
        # renvoyer la conversation telle quelle pour qu'elle reprenne.
        continuations = 0
        while response.stop_reason == "pause_turn" and continuations < MAX_CONTINUATIONS:
            response = _call_claude(client, [user_message, {"role": "assistant", "content": response.content}])
            _accumulate_usage(usage, response)
            continuations += 1
    except anthropic.AuthenticationError as exc:
        raise ScenarioGenerationError(
            "Clé API Anthropic manquante ou invalide (ANTHROPIC_API_KEY).", usage=_finalize_usage(usage)
        ) from exc
    except anthropic.RateLimitError as exc:
        raise ScenarioGenerationError(
            "Limite de requêtes Anthropic atteinte, réessayez dans un instant.", usage=_finalize_usage(usage)
        ) from exc
    except anthropic.APIError as exc:
        raise ScenarioGenerationError(f"Erreur de l'API Anthropic : {exc}", usage=_finalize_usage(usage)) from exc
    except Exception as exc:
        # Couvre notamment l'absence totale de clé API (ANTHROPIC_API_KEY non
        # définie), qui échoue avant même d'obtenir une exception anthropic.*.
        raise ScenarioGenerationError(
            f"Clé API Anthropic non configurée ou erreur inattendue : {exc}", usage=_finalize_usage(usage)
        ) from exc

    _finalize_usage(usage)

    if response.stop_reason == "refusal":
        raise ScenarioGenerationError("Le modèle a refusé de traiter cette demande.", usage=usage)
    if response.stop_reason == "max_tokens":
        raise ScenarioGenerationError(
            "La réponse du modèle a été tronquée (limite de tokens atteinte avant la fin de la génération).",
            usage=usage,
        )

    text_parts = [block.text for block in response.content if block.type == "text"]
    full_text = "\n".join(text_parts).strip()
    if not full_text:
        raise ScenarioGenerationError(
            f"Le modèle n'a renvoyé aucun texte exploitable (stop_reason : {response.stop_reason}).", usage=usage
        )

    try:
        data = _extract_json_array(full_text)
    except (ValueError, re.error) as exc:
        raise ScenarioGenerationError("Réponse du modèle illisible (JSON invalide).", usage=usage) from exc

    if not isinstance(data, list):
        raise ScenarioGenerationError("Le modèle n'a pas renvoyé une liste de scénarios.", usage=usage)

    scenarios = []
    for item in data:
        if not isinstance(item, dict) or not all(k in item for k in REQUIRED_KEYS):
            continue
        scenarios.append({k: str(item.get(k, "")).strip() for k in REQUIRED_KEYS})

    if not scenarios:
        raise ScenarioGenerationError("Aucun scénario exploitable dans la réponse du modèle.", usage=usage)

    return scenarios[:num_to_generate], usage
