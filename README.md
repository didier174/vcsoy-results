# VCSOY RESULTS — version web

Version web de l'outil de traitement des résultats ESCDA Canada, destinée à
être utilisée par vous et vos collaborateurs à l'adresse `app.ca2d.ca`,
hébergée sur [Render](https://render.com).

## Contrôle d'accès (liste blanche)

Par défaut (`ALLOWED_EMAILS` vide), n'importe quel compte Google valide peut
se connecter. **Pour restreindre l'accès à vos collaborateurs**, définissez
la variable d'environnement `ALLOWED_EMAILS` avec la liste des adresses
autorisées, séparées par des virgules :

```
ALLOWED_EMAILS=didier@escda.ca,alexandra@escda.ca,collegue@gmail.com
```

Cette liste s'applique à la fois à la connexion Google et à la connexion
simplifiée (mode développement). Elle est indépendante de la liste des
« utilisateurs test » configurée côté Google Cloud Console : c'est la vraie
barrière de sécurité côté application, qui continuera de fonctionner même
si l'écran de consentement Google est un jour publié.

À définir dans votre `.env` local, **et** dans les variables d'environnement
du service sur Render (Settings → Environment).

## Étape 1 (web) — Ossature

Reproduit la même logique que la version Mac :
- Écran de connexion (via **Google**, ou par simple e-mail en mode
  développement local)
- Une fois connecté : logo de l'édition en cours (taille moyenne + rappel en
  gras), cliquable pour changer d'édition, menu latéral avec les 9 items
- Chaque utilisateur a **sa propre édition sélectionnée** (stockée dans son
  cookie de session) — deux collaborateurs peuvent travailler sur des
  éditions différentes en même temps sans se gêner
- Toutes les actions sont journalisées dans la table `action_log`

« Configuration catégorie » et « Configuration Participant » seront portées
dans les prochaines étapes ; les autres items du menu affichent un écran
d'attente pour l'instant.

## Étape 2 (web) — Configuration catégorie

Tableau (case à cocher, Category Name, Nom de la Catégorie, **Code**) avec
« Ajouter » (ligne éditable immédiatement), « Modifier » (lignes cochées
passent en édition), « Enregistrer » (avec contrôle des champs
obligatoires), « Annuler ». Le **code doit être composé d'exactement 2
chiffres** et être **unique au sein de l'édition** (il sert à identifier la
catégorie dans les ID de test — voir étape 4). Données rattachées à
l'édition en cours.

## Étape 3 (web) — Configuration Participant

Tableau avec case à cocher, Participants Name, Category Name, **Code**, et
**Act Ref.** (case à cocher directement modifiable, enregistrée
immédiatement). « Ajouter »/« Modifier » ouvrent une page de saisie dédiée
(l'équivalent web de la fenêtre qui s'affichait par-dessus l'écran
principal côté Mac), avec un nouveau champ **Code** obligatoire (2
chiffres, **unique au sein de sa catégorie**), tous les champs du modèle
fourni, adresse de facturation pré-remplie automatiquement depuis l'adresse
du participant (case à décocher pour la saisir manuellement), et validation
des champs obligatoires (nom, code, catégorie, représentant, au moins un
canal à tester).

Comme sur Mac, « Modifier » n'accepte qu'un seul participant sélectionné à
la fois.

## Étape 4 (web) — Chargement d'un fichier de résultat

Permet de charger le fichier Excel de résultats de tests mystères (onglets
Phone, Email, Web Navigation, Social Networks, Chat).

Le chargement est **tout-ou-rien** : le fichier entier est d'abord
entièrement vérifié ; s'il contient la moindre erreur, **rien n'est
enregistré** et la liste complète des erreurs est affichée
(« Onglet X — Ligne Y erreur cellule Z : … ») pour permettre la correction
avant un nouveau chargement.

**Contrôles effectués sur chaque ligne non vide :**
- Colonne A (ID Mystery Test) : doit faire 8 chiffres, sous la forme
  CCPPXXXX, où CC correspond à un code de catégorie existant (édition en
  cours), PP à un code de participant existant *dans cette catégorie*, et
  XXXX à un numéro dans la plage attendue pour l'onglet (Phone 1200-1299,
  Email 1300-1339, Web Navigation 1350-1364, Social Networks 1400-1409,
  Chat 1450-1459).
- Toute colonne « Code N » ne peut contenir que 0, 1, 2 ou « Non
  applicable » (vide accepté). Les colonnes « Code N obs » ne sont pas
  contrôlées (tout est accepté, y compris vide).
- « Id Mystery Tester » est obligatoire dès qu'une ligne a un ID Mystery
  Test rempli. Sur l'onglet Phone spécifiquement, Call_Date, Call_hour et
  Call Duration sont également obligatoires.

**Une fois le fichier validé sans erreur**, chaque test est enregistré en
base (table `test_result`), rattaché à sa catégorie et son participant. Un
nouveau chargement portant sur un ID Mystery Test déjà présent **met à
jour** l'enregistrement existant plutôt que de créer un doublon — pratique
pour recharger un fichier corrigé ou mis à jour.

Toutes les colonnes brutes de chaque ligne (Code 1 à 15, leurs
observations, les champs spécifiques au canal comme QS, Status, Note
brute...) sont conservées telles quelles, pour que les futures étapes
(calcul du score, présentation des résultats) puissent s'appuyer dessus
sans changement de schéma de base de données.

> **Point d'attention testé et confirmé sur votre fichier d'exemple** :
> celui-ci contient volontairement des erreurs (Id Mystery Tester manquant
> sur toutes les lignes, valeurs invalides dans plusieurs colonnes Code —
> notamment « Non observable » utilisé au lieu de « Non applicable », qui
> n'est pas dans la liste des valeurs autorisées par le prompt). L'outil les
> détecte toutes (37 erreurs sur ce fichier). Si « Non observable » doit en
> réalité être une valeur valide, dites-le-moi et j'ajuste la règle.

---

## 1. Tester en local (avant tout déploiement)

> **Si vous avez déjà testé une version précédente en local** : supprimez
> d'abord le fichier `vcsoy_dev.db` (dans le dossier `vcsoy_web`) avant de
> relancer l'application, pour que la base locale soit recréée avec le
> nouveau schéma (colonne `code` sur les participants, nouvelle table des
> résultats de tests). Vos données locales de test seront perdues, mais rien
> de tout cela n'affecte la base de données réelle sur Render.
> ```bash
> rm -f vcsoy_dev.db
> ```

```bash
cd vcsoy_web
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Ouvrez `.env` et changez au minimum `SECRET_KEY` par une chaîne aléatoire.
Laissez `GOOGLE_CLIENT_ID` et `GOOGLE_CLIENT_SECRET` vides pour l'instant —
`ALLOW_DEV_LOGIN=1` permet de se connecter avec une simple adresse e-mail
tant que Google n'est pas configuré.

```bash
export $(cat .env | xargs)   # charge les variables dans le terminal (macOS/Linux)
flask --app wsgi run
```

Ouvrez `http://localhost:5000` — vous devriez voir l'écran de connexion.
Une base SQLite locale (`vcsoy_dev.db`) est créée automatiquement au premier
lancement, aucune installation de base de données n'est nécessaire pour
tester.

---

## 2. Mettre le code sur GitHub

```bash
cd vcsoy_web
git init
git add .
git commit -m "Version web - étape 1 : ossature"
```

Créez un nouveau dépôt **vide** sur [github.com/new](https://github.com/new)
(par exemple `vcsoy-results`), puis :

```bash
git remote add origin https://github.com/VOTRE_COMPTE/vcsoy-results.git
git branch -M main
git push -u origin main
```

---

## 3. Configurer la connexion Google (Google Cloud Console)

1. Allez sur [console.cloud.google.com](https://console.cloud.google.com/)
   et créez un nouveau projet (ex. « VCSOY Results »).
2. Menu **API et services** → **Écran de consentement OAuth** : type
   "Externe", renseignez le nom de l'app et votre e-mail, enregistrez.
3. Menu **API et services** → **Identifiants** → **Créer des identifiants**
   → **ID client OAuth** → type **Application Web**.
4. Dans **URI de redirection autorisés**, ajoutez (vous pourrez compléter
   plus tard) :
   - `http://localhost:5000/auth/google/callback` (pour vos tests en local)
5. Une fois créé, copiez le **Client ID** et le **Client Secret** — vous en
   aurez besoin à l'étape 4 (Render) et pourrez aussi les mettre dans votre
   `.env` local pour tester la vraie connexion Google en local.

---

## 4. Déployer sur Render

### Option recommandée : déploiement par Blueprint (app + base de données en un clic)

1. Sur [dashboard.render.com](https://dashboard.render.com), cliquez **New**
   → **Blueprint**.
2. Connectez votre compte GitHub et sélectionnez le dépôt `vcsoy-results`.
   Render détecte automatiquement le fichier `render.yaml` inclus dans le
   projet et propose de créer :
   - un service web (`vcsoy-results`)
   - une base de données PostgreSQL (`vcsoy-results-db`)
3. Render vous demandera de renseigner `GOOGLE_CLIENT_ID` et
   `GOOGLE_CLIENT_SECRET` (les seules variables non générées
   automatiquement) — collez les valeurs obtenues à l'étape 3.
4. Cliquez **Apply**. Le premier déploiement prend quelques minutes.
5. Une fois terminé, Render vous donne une adresse temporaire du type
   `https://vcsoy-results.onrender.com` — l'application est déjà utilisable
   à cette adresse.

### Étape suivante : ajouter le callback Google pour cette adresse

Retournez dans Google Cloud Console → Identifiants → votre client OAuth, et
ajoutez cette URI de redirection supplémentaire :
`https://vcsoy-results.onrender.com/auth/google/callback`
(remplacez par votre adresse réelle si différente).

---

## 5. Brancher le domaine app.ca2d.ca

1. Dans Render, ouvrez le service `vcsoy-results` → **Settings** → **Custom
   Domains** → **Add Custom Domain** → entrez `app.ca2d.ca`.
2. Render affiche la **valeur exacte** à utiliser comme cible CNAME (ce sera
   très probablement `vcsoy-results.onrender.com`, à confirmer dans l'écran
   Render).
3. Retournez dans le Manager OVH → `ca2d.ca` → **Zone DNS** → modifiez
   l'entrée `app` déjà créée pour qu'elle pointe vers cette valeur exacte
   (au lieu du nom d'exemple utilisé précédemment).
4. Ajoutez aussi cette URI de redirection dans Google Cloud Console :
   `https://app.ca2d.ca/auth/google/callback`
5. Une fois le DNS propagé (quelques minutes à quelques heures), Render
   génère automatiquement le certificat HTTPS pour `app.ca2d.ca`.

---

## 6. Finaliser pour la production

Une fois la connexion Google testée et validée sur `app.ca2d.ca` :

- Dans Render → **Environment**, mettez `ALLOW_DEV_LOGIN` à `0` (déjà fait
  par défaut dans `render.yaml`) pour ne garder que la connexion Google.
- Vérifiez que `SECRET_KEY` a bien été générée automatiquement par Render
  (c'est le cas par défaut avec `render.yaml`).

---

## ⚠️ Migration de base de données nécessaire (important, à faire avant de redéployer)

Cette livraison **ajoute une colonne à une table qui existe déjà** sur
Render (`code` sur la table `participant`). `db.create_all()` crée
uniquement les tables manquantes — il ne modifie jamais une table
existante. Sans cette étape, l'application plantera dès qu'elle touchera
la table `participant` une fois déployée.

**Avant de pousser ce code sur Render**, connectez-vous à votre base
PostgreSQL Render et exécutez :

```sql
ALTER TABLE participant ADD COLUMN IF NOT EXISTS code VARCHAR(2) DEFAULT '';
```

Comment l'exécuter : Dashboard Render → votre base `vcsoy-results-db` →
bouton **Connect** → copiez la commande `psql` proposée, collez-la dans
votre Terminal, puis collez la commande SQL ci-dessus une fois connecté.

(Les tables `category` et `test_result`, elles, sont entièrement
nouvelles : `db.create_all()` les crée automatiquement sans manipulation
de votre part.)

## À propos de la base de données

Cette version ajoute deux nouvelles tables (`category` et `participant`).
Elles sont créées **automatiquement** au démarrage de l'application
(`db.create_all()`) — aucune manipulation de base de données n'est
nécessaire de votre côté, ni en local ni sur Render. Les données déjà
présentes (utilisateurs, historique) ne sont pas touchées.

## Étape 5 (web) — Listes des tests

Item de menu renommé de « Présentation de la liste de test » en **« Listes
des tests »**.

Les tests sont présentés **groupés par participant** (avec rappel de la
catégorie), puis par canal. **Important** : la signification d'un « Code
N » dépend du canal (Code 3 en téléphone ≠ Code 3 en chat) — chaque test
affiche donc uniquement ses propres codes, sans jamais mélanger des
colonnes de canaux différents dans un même tableau.

Pour chaque test : date, canal, et la liste des « Code N » sous forme de
petites puces cliquables — un clic ouvre une popup avec la valeur du code
et son observation associée (colonne « Code N obs », retrouvée même quand
son nom exact varie légèrement, ex. « Code3 obs » vs « Code 9 obs »). Un
bouton « Autres données » ouvre une popup listant tous les autres champs
de la ligne (Id Mystery Tester, QS, Status, etc.).

Un bouton **« Rechercher un test »** ouvre une popup de recherche (numéro
de test, canal et/ou date — au moins un critère) ; le ou les tests
correspondants sont ensuite présentés avec toutes leurs informations dans
une page de détail claire et complète (mêmes données que les popups, mais
organisées pour une lecture d'ensemble).

Techniquement : popups réalisées avec l'élément natif `<dialog>` du
navigateur (aucune bibliothèque JS externe), et les données nécessaires
aux popups de la liste sont embarquées directement dans la page au
chargement (pas d'aller-retour réseau supplémentaire au clic).

## Étape 6 (web) — Administration

Nouvel item de menu **« Administration »**, qui permet de gérer la liste
des utilisateurs autorisés à se connecter (ajout par adresse e-mail,
suppression), en complément de la variable d'environnement
`ALLOWED_EMAILS` (dont les adresses restent affichées mais ne sont pas
modifiables depuis cet écran, car elles proviennent de la configuration
serveur). Cette liste est globale, indépendante de l'édition en cours.

Le bouton « Rechercher un test » (étape 5) a aussi été déplacé en haut de
la page « Listes des tests », au-dessus des résultats plutôt qu'en bas.

## Étape 7 (web) — Facturation

Nouvel item de menu **« Facturation »**, qui permet de générer une facture
pour un participant de l'édition en cours : langue (français/anglais),
numéro de facture, numéro de client, nom du client, date, sélection du
participant puis des produits à facturer (le forfait VCSOY — présenté sur
4 lignes mais facturé comme un seul produit — et des produits
indépendants comme le droit d'usage de la marque ou les goodies).

Les taxes du Québec (TPS 5 % + TVQ 9,975 %) sont calculées et appliquées
automatiquement, sauf pour un participant dont l'adresse de facturation
est hors Canada (exportation de services détaxée à 0 %, comme prévu par
le modèle de facture fourni).

La facture est téléchargeable en Excel (à partir du modèle fourni, pour
permettre des ajustements manuels) et en PDF, et peut être modifiée ou
supprimée depuis la liste des factures.

## Structure du projet

```
vcsoy_web/
├── wsgi.py                    # point d'entrée (gunicorn en production)
├── requirements.txt
├── render.yaml                 # déploiement Render en un clic (app + DB)
├── Procfile                    # alternative de déploiement manuel
├── .env.example
├── app/
│   ├── __init__.py             # create_app() (fabrique de l'application)
│   ├── config.py                # configuration (variables d'environnement)
│   ├── extensions.py            # db, login_manager, oauth
│   ├── models.py                # User, ActionLog, Category, Participant, TestResult
│   ├── editions.py              # éditions + édition courante (par session utilisateur)
│   ├── menu.py                  # liste centralisée des items du menu latéral
│   ├── access_control.py        # liste blanche des e-mails autorisés
│   ├── auth/routes.py            # connexion (Google + mode développement)
│   ├── main/routes.py            # dashboard, menu, changement d'édition
│   ├── categories/routes.py      # Configuration catégorie
│   ├── participants/routes.py    # Configuration Participant
│   ├── results/
│   │   ├── routes.py              # Chargement de fichier + Listes des tests + recherche
│   │   ├── validation.py          # Règles de contrôle du fichier Excel
│   │   └── presentation.py        # Extraction Code N / observation / autres données
│   ├── templates/                # gabarits HTML (Jinja2)
│   └── static/
│       ├── css/style.css
│       ├── js/                   # petits scripts (popups, bascule Act Ref., adresse facturation)
│       └── img/                  # logos des éditions
```

## À propos des tests

Je n'ai pas d'accès Internet dans mon environnement de travail pour
installer Flask-SQLAlchemy / Flask-Login / Authlib. J'ai donc construit de
petites versions simulées de ces bibliothèques (non incluses dans ce
livrable) pour exécuter réellement les routes de l'application avec le vrai
client de test Flask. `openpyxl`, lui, est réellement disponible dans mon
environnement : le moteur de validation du fichier de résultats (étape 4) a
donc été testé **directement contre votre fichier d'exemple réel**
(`test_Tire__result__ESCDA_2027.xlsx`), sans simulation — les 37 erreurs
qu'il contient sont détectées correctement, et un fichier construit sans
erreur se charge et s'enregistre bien en base.

J'ai aussi vérifié : connexion (mode développement **et** Google simulé),
liste blanche des e-mails, redirections de protection des pages,
changement d'édition, déconnexion, CRUD complet catégories/participants
avec les nouveaux codes à 2 chiffres (format + unicité), chargement de
fichier (erreurs détectées, chargement réussi, mise à jour sans doublon en
cas de rechargement), et absence de régression sur tout ce qui existait
déjà. Tout est passé. La dernière validation qu'il vous reste à faire est
de tester avec les **vraies** bibliothèques en conditions réelles.

## Prochaines étapes

Compilation des résultats (calcul du score par participant à partir des
données maintenant en base), détermination des gagnants par catégorie,
présentation des résultats, liste des lauréats — au fur et à mesure de vos
indications.

Aucune migration de base de données n'est nécessaire pour cette étape
(aucune nouvelle table, aucune nouvelle colonne sur une table existante).
