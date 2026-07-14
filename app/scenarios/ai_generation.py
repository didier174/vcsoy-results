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
    pass


def _build_prompt(participant_name, website_url, problematiques_text, examples, num_to_generate):
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
        raise ScenarioGenerationError("Réponse du modèle sans tableau JSON exploitable.")
    return json.loads(text[start : end + 1])


MAX_TOKENS = 16000
MAX_CONTINUATIONS = 3


def generate_scenarios(participant_name, website_url, problematiques_text, examples, num_to_generate=10):
    """
    Retourne une liste de dicts {type, contexte, question, reponse, url_source},
    de longueur <= num_to_generate. Lève ScenarioGenerationError en cas d'échec.
    """
    prompt = _build_prompt(participant_name, website_url, problematiques_text, examples, num_to_generate)
    user_message = {"role": "user", "content": prompt}

    try:
        # timeout généreux : la recherche web + génération de 10 scénarios
        # peut prendre plusieurs minutes (voir --timeout gunicorn dans
        # render.yaml, qui doit rester supérieur à cette valeur).
        client = anthropic.Anthropic(timeout=480.0)
        tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 10}]

        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            tools=tools,
            messages=[user_message],
        )

        # La recherche web est traitée côté serveur ; si elle atteint sa
        # limite interne d'itérations, l'API renvoie "pause_turn" et il faut
        # renvoyer la conversation telle quelle pour qu'elle reprenne.
        continuations = 0
        while response.stop_reason == "pause_turn" and continuations < MAX_CONTINUATIONS:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
                tools=tools,
                messages=[user_message, {"role": "assistant", "content": response.content}],
            )
            continuations += 1
    except anthropic.AuthenticationError as exc:
        raise ScenarioGenerationError("Clé API Anthropic manquante ou invalide (ANTHROPIC_API_KEY).") from exc
    except anthropic.RateLimitError as exc:
        raise ScenarioGenerationError("Limite de requêtes Anthropic atteinte, réessayez dans un instant.") from exc
    except anthropic.APIError as exc:
        raise ScenarioGenerationError(f"Erreur de l'API Anthropic : {exc}") from exc
    except Exception as exc:
        # Couvre notamment l'absence totale de clé API (ANTHROPIC_API_KEY non
        # définie), qui échoue avant même d'obtenir une exception anthropic.*.
        raise ScenarioGenerationError(f"Clé API Anthropic non configurée ou erreur inattendue : {exc}") from exc

    if response.stop_reason == "refusal":
        raise ScenarioGenerationError("Le modèle a refusé de traiter cette demande.")
    if response.stop_reason == "max_tokens":
        raise ScenarioGenerationError(
            "La réponse du modèle a été tronquée (limite de tokens atteinte avant la fin de la génération)."
        )

    text_parts = [block.text for block in response.content if block.type == "text"]
    full_text = "\n".join(text_parts).strip()
    if not full_text:
        raise ScenarioGenerationError(
            f"Le modèle n'a renvoyé aucun texte exploitable (stop_reason : {response.stop_reason})."
        )

    try:
        data = _extract_json_array(full_text)
    except (ValueError, re.error) as exc:
        raise ScenarioGenerationError("Réponse du modèle illisible (JSON invalide).") from exc

    if not isinstance(data, list):
        raise ScenarioGenerationError("Le modèle n'a pas renvoyé une liste de scénarios.")

    scenarios = []
    for item in data:
        if not isinstance(item, dict) or not all(k in item for k in REQUIRED_KEYS):
            continue
        scenarios.append({k: str(item.get(k, "")).strip() for k in REQUIRED_KEYS})

    if not scenarios:
        raise ScenarioGenerationError("Aucun scénario exploitable dans la réponse du modèle.")

    return scenarios[:num_to_generate]
