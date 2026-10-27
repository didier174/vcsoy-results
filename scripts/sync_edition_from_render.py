"""
Copie UNE édition de la base de production (Render, PostgreSQL) vers la base locale de développement (SQLite),
pour travailler en local sur exactement les mêmes données que app.ca2d.ca (vérifier des calculs, générer des
rapports d'étude, etc.).

Usage (depuis la racine du projet) :
    set RENDER_DATABASE_URL=postgresql://utilisateur:mot_de_passe@hote/base      (PowerShell : $env:RENDER_DATABASE_URL="...")
    venv\\Scripts\\python.exe scripts\\sync_edition_from_render.py 2027 [--templates]

Pourquoi ce script est écrit ainsi :
- La base Render n'est lue qu'en LECTURE SEULE (transaction read-only, uniquement des SELECT) ; l'URL n'est
  lue que dans la variable d'environnement RENDER_DATABASE_URL, jamais stockée dans un fichier.
- On n'écrit QUE dans la base locale, et le script refuse de tourner si la base cible n'est pas SQLite (garde-fou
  contre une DATABASE_URL qui pointerait par erreur sur la production).
- Rejouable : les lignes locales de l'édition sont d'abord supprimées puis recopiées, en une seule transaction
  (tout ou rien). Les autres éditions locales (« blanche », « FAKEREPRO »...) ne sont jamais touchées.
- Les identifiants numériques sont recréés localement (ceux de Render peuvent entrer en collision avec les lignes
  locales) et les clés étrangères category_id / participant_id sont remappées. Les liens vers les utilisateurs
  (uploaded_by_id...) sont mis à NULL : la table des utilisateurs n'est pas copiée.
- Le cache d'agrégats (edition_report_cache) n'est pas copié : il dépend du code local ; il se recalcule via
  « Liste des lauréats » ou report_cache.refresh_edition_cache.
- --templates copie aussi les modèles de rapport d'étude de l'édition (fichiers volumineux), désactivé par défaut.
"""
import os
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Category, FileUpload, Participant, ReportTemplate, TestResult  # noqa: E402

USER_LINKS = {"uploaded_by_id", "computed_by_id", "created_by_id"}


def read_remote(url, edition_id, with_templates):
    con = psycopg2.connect(url, sslmode="require", connect_timeout=20)
    con.set_session(readonly=True, autocommit=True)
    cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def rows(table, where="edition_id = %s"):
        cur.execute(f"SELECT * FROM {table} WHERE {where} ORDER BY id", (edition_id,))
        return [dict(r) for r in cur.fetchall()]

    data = {
        "category": rows("category"),
        "participant": rows("participant"),
        "test_result": rows("test_result"),
        "file_upload": rows("file_upload"),
        "report_template": rows("report_template") if with_templates else [],
    }
    con.close()
    return data


def clean(model, row):
    """Colonnes du modèle local, sans l'identifiant ni les liens vers la table des utilisateurs."""
    cols = {c.name for c in model.__table__.columns}
    return {k: v for k, v in row.items() if k in cols and k != "id" and k not in USER_LINKS}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    edition_id = args[0]
    with_templates = "--templates" in sys.argv
    url = os.environ.get("RENDER_DATABASE_URL")
    if not url:
        sys.exit("Variable d'environnement RENDER_DATABASE_URL manquante.")

    app = create_app()
    with app.app_context():
        target = str(db.engine.url)
        if not target.startswith("sqlite"):
            sys.exit("Refus d'écrire : la base cible n'est pas SQLite locale (" + target.split("@")[-1] + ").")

        remote = read_remote(url, edition_id, with_templates)
        if not remote["test_result"]:
            sys.exit(f"Aucun test pour l'édition « {edition_id} » sur Render : rien copié.")

        # Suppression des lignes locales de cette édition (ordre : enfants avant parents)
        local_ids = [t.id for t in TestResult.query.filter_by(edition_id=edition_id).all()]
        if local_ids:
            from app.test_deletion import delete_test_dependents  # enfants éventuels (records, sélections...)
            delete_test_dependents(local_ids)
        TestResult.query.filter_by(edition_id=edition_id).delete(synchronize_session=False)
        FileUpload.query.filter_by(edition_id=edition_id).delete(synchronize_session=False)
        Participant.query.filter_by(edition_id=edition_id).delete(synchronize_session=False)
        Category.query.filter_by(edition_id=edition_id).delete(synchronize_session=False)
        if with_templates:
            ReportTemplate.query.filter_by(edition_id=edition_id).delete(synchronize_session=False)
        db.session.flush()

        # Copie avec remappage des identifiants
        cat_map, part_map = {}, {}
        for r in remote["category"]:
            obj = Category(**clean(Category, r))
            db.session.add(obj)
            db.session.flush()
            cat_map[r["id"]] = obj.id
        for r in remote["participant"]:
            d = clean(Participant, r)
            d["category_id"] = cat_map.get(r.get("category_id"))
            obj = Participant(**d)
            db.session.add(obj)
            db.session.flush()
            part_map[r["id"]] = obj.id
        for r in remote["test_result"]:
            d = clean(TestResult, r)
            d["category_id"] = cat_map.get(r.get("category_id"))
            d["participant_id"] = part_map.get(r.get("participant_id"))
            db.session.add(TestResult(**d))
        for r in remote["file_upload"]:
            db.session.add(FileUpload(**clean(FileUpload, r)))
        for r in remote["report_template"]:
            db.session.add(ReportTemplate(**clean(ReportTemplate, r)))
        db.session.commit()

        print(f"Édition « {edition_id} » copiée de Render vers {target} :")
        print(f"  catégories {len(remote['category'])} | participants {len(remote['participant'])} | "
              f"tests {len(remote['test_result'])} | chargements {len(remote['file_upload'])} | "
              f"modèles {len(remote['report_template'])}")


if __name__ == "__main__":
    main()
