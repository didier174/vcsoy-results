"""
Génère un rapport d'étude (.pptx) à partir d'un modèle et d'un
dictionnaire de valeurs, en remplaçant les balises {{ Nom de la balise }}
dans tous les textes du modèle (titres, zones de texte, tableaux, formes
groupées).

Contrainte PowerPoint : le texte d'un même paragraphe visible peut être
réparti sur plusieurs "runs" XML (changement de police au milieu d'un mot,
correction automatique, etc.), donc une balise peut être coupée en deux
runs différents. On reconstitue le texte complet du paragraphe pour
repérer/remplacer les balises, puis on réécrit le résultat dans le
premier run (en vidant les suivants) pour ne pas perdre le formatage.
"""

import io
import re

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

TAG_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def _iter_shapes(shapes):
    for shape in shapes:
        yield shape
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _iter_shapes(shape.shapes)


def _iter_paragraphs(shape):
    if getattr(shape, "has_text_frame", False):
        yield from shape.text_frame.paragraphs
    if getattr(shape, "has_table", False):
        for row in shape.table.rows:
            for cell in row.cells:
                yield from cell.text_frame.paragraphs


def _paragraph_text(paragraph):
    return "".join(run.text for run in paragraph.runs)


def _normalize(tag):
    return tag.strip().lower()


def _substitute_paragraph(paragraph, lookup):
    full_text = _paragraph_text(paragraph)
    if "{{" not in full_text:
        return

    new_text = TAG_RE.sub(lambda m: str(lookup.get(_normalize(m.group(1)), m.group(0))), full_text)
    if new_text == full_text or not paragraph.runs:
        return

    paragraph.runs[0].text = new_text
    for run in paragraph.runs[1:]:
        run.text = ""


def find_tags(template_bytes):
    """Retourne l'ensemble des noms de balises {{ ... }} présentes dans le modèle."""
    prs = Presentation(io.BytesIO(template_bytes))
    tags = set()
    for slide in prs.slides:
        for shape in _iter_shapes(slide.shapes):
            for paragraph in _iter_paragraphs(shape):
                tags.update(TAG_RE.findall(_paragraph_text(paragraph)))
    return tags


def render_template(template_bytes, values):
    """
    template_bytes : contenu binaire du modèle .pptx.
    values : dict {nom de balise: valeur}. La correspondance balise/clé
    ignore la casse et les espaces superflus (ex. {{ PARTICIPANT }} et
    {{ participant }} pointent tous deux vers la clé "Participant").

    Retourne (bytes du .pptx généré, ensemble des balises inconnues
    rencontrées dans le modèle mais absentes de `values`).
    """
    prs = Presentation(io.BytesIO(template_bytes))
    lookup = {_normalize(key): value for key, value in values.items()}

    unknown = set()
    for slide in prs.slides:
        for shape in _iter_shapes(slide.shapes):
            for paragraph in _iter_paragraphs(shape):
                text = _paragraph_text(paragraph)
                unknown.update(tag for tag in TAG_RE.findall(text) if _normalize(tag) not in lookup)
                _substitute_paragraph(paragraph, lookup)

    out = io.BytesIO()
    prs.save(out)
    return out.getvalue(), unknown
