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

## Étape 8 (web) — Compilation des résultats

Nouvel item de menu **« Compilation des résultats »**, qui calcule et
affiche la note de chaque participant à partir des tests déjà chargés
(« Chargement fichier résultat »).

**Calcul de la note d'un test** : on additionne la valeur (0, 1 ou 2) de
chaque colonne « Code N » renseignée (une valeur vide ou « Non
applicable » exclut ce critère du calcul, aussi bien du numérateur que du
dénominateur). Un code précis, propre à chaque canal, compte double :
Code 13 pour Phone, Code 11 pour Mail/Web Navigation/Social Networks, Code
10 pour Chat. La **note brute** obtenue est ramenée sur 20 (proportionnellement
au maximum atteignable compte tenu du nombre de critères réellement
valides pour ce test), ce qui permet de comparer des tests ayant des
critères « Non applicable » différents ou appartenant à des canaux dont
le nombre total de codes diffère (13 à 15 selon le canal).

**Tableau affiché** : un participant par ligne (nom, code de la
catégorie), avec pour chacun des 5 canaux le nombre de tests pris en
compte et la note moyenne sur 20 de ce canal, puis une **note consolidée**
pour l'ensemble de ses tests (tous canaux confondus) — présentée à la
fois en note brute (ramenée sur l'échelle 0-32) et sur 20, cette dernière
étant la référence qui servira au classement par catégorie dans la
prochaine étape (« Présentation des résultats »).

Cliquer sur le nom d'un participant ouvre une popup listant tous ses
tests pris en compte (numéro de test, canal, note brute et note sur 20),
avec défilement (jusqu'à 200 tests pour un même participant).

> **Point d'attention** : le mode de calcul de la note consolidée
> (tous canaux confondus) n'était pas précisé dans le détail — j'ai retenu
> la moyenne simple des notes sur 20 de tous les tests du participant
> (chaque test pesant le même poids, quel que soit son canal). Si vous
> souhaitez plutôt pondérer différemment les canaux entre eux, dites-le-moi
> et j'ajuste le calcul.

Aucune migration de base de données n'est nécessaire pour cette étape : le
calcul se fait à la volée à partir des données déjà en base
(`test_result.raw_data`), rien n'est stocké de nouveau.

## Étape 8 bis — Trois correctifs

**1. Contrôle du canal actif au chargement d'un fichier de résultat.**
Un test n'est désormais accepté que si le canal de l'onglet (Phone, Email,
Web Navigation, Social Networks, Chat) est déclaré actif pour le
participant visé (case cochée dans Configuration Participant). Comme pour
les autres règles, le chargement est tout-ou-rien : si un seul test porte
sur un canal non actif, rien n'est enregistré. Une popup dédiée s'affiche
en plus de la liste d'erreurs habituelle, pour indiquer clairement quel(s)
canal(aux) posent problème et pour quel(s) participant(s).

**2. Fichiers déjà chargés introuvables dans la liste.** Le modèle qui
garde l'historique des chargements (`FileUpload`) a été ajouté après coup
(étape 7 bis) — les fichiers chargés avant cette étape n'ont donc jamais eu
de ligne correspondante, même si leurs tests sont bien en base. La page
reconstruit maintenant automatiquement, une fois pour toutes, l'historique
manquant à partir des tests déjà enregistrés (`test_result.source_filename`
/ `uploaded_at` / `uploaded_by_id`, présents depuis le tout premier
chargement) : aucune perte de données, aucune manipulation de votre part.

**3. Compilation des résultats : mauvais code affiché.** La colonne
« Cat » affichait par erreur le code du **participant** (01, 02, 03...) au
lieu du code de la **catégorie**. Corrigé.

Aucune migration de base de données n'est nécessaire pour ces correctifs.

## Étape 8 ter — Trois améliorations

**1. Liste des tests : renommage et compteur.** L'item de menu « Listes
des tests » devient **« Liste des tests »** ; le nombre total de tests en
base pour l'édition en cours est affiché en haut à droite de la page.

**2. Chargement fichier résultat : annuler un fichier.** Un bouton
**« Annuler un fichier »** permet de choisir, parmi les fichiers déjà
chargés, celui à annuler : toutes les données de test qui en proviennent
sont alors **supprimées définitivement** de la base (et le fichier
disparaît de la liste). Une **double confirmation** est exigée (une case à
cocher à cocher explicitement, puis une confirmation navigateur), l'action
étant irréversible.

**3. Compilation des résultats : accès au détail d'un test.** Dans la
popup listant les tests d'un participant, l'« Id Mystery Test » est
maintenant affiché en gras et cliquable : un clic ouvre la page de détail
du test, la même que celle obtenue en cherchant un test dans « Liste des
tests » et en cliquant dessus.

Aucune migration de base de données n'est nécessaire pour ces
améliorations.

## Étape 9 (web) — Liste des résultats et Liste des lauréats

> **Renommage** : l'item de menu « Présentation des résultats » (jusque-là
> un écran d'attente) devient **« Liste des résultats »**, pour porter la
> fonctionnalité décrite ci-dessous.

**Liste des résultats.** Tableau succinct : un participant par ligne, avec
le nom, le code de sa catégorie, et sa **note finale par canal** (moyenne
des notes sur 20 de ses tests pour ce canal — la même valeur que dans
Compilation des résultats). Deux boutons ouvrent chacun une popup :
- **Résultats par canal par catégorie** : choisissez une catégorie et un
  canal, la popup liste les participants de cette catégorie avec leur note
  pour ce canal, du meilleur au moins bon.
- **Résultats par canal toute catégorie** : choisissez un canal, la popup
  liste tous les participants de l'édition (toutes catégories) avec leur
  note pour ce canal, du meilleur au moins bon.

En dessous, un tableau **« Gagnants par catégorie »** affiche, pour
chaque catégorie, le participant en tête et sa **note finale consolidée**.

**Note finale consolidée.** Elle pondère les notes par canal d'un
participant selon l'ensemble exact des canaux sur lesquels il a des tests
comptabilisés (les canaux sans aucun test ne comptent pas) :

| Canaux testés | Pondération | Multiplicateur |
|---|---|---|
| Phone, Mail, Web, RS, Chat | 0,57 / 0,23 / 0,08 / 0,06 / 0,06 | — |
| Phone, Mail, Web, RS | 0,6 / 0,24 / 0,09 / 0,07 | × 0,98 |
| Phone, Mail, Web, Chat | 0,6 / 0,24 / 0,09 / 0,07 | × 0,98 |
| Phone, Mail, Web | 0,63 / 0,27 / 0,1 | × 0,95 |
| Phone, Web, RS, Chat | 0,70 / 0,14 / 0,08 / 0,08 | × 0,90 |
| Phone, Web, Chat | 0,75 / 0,15 / 0,1 | × 0,85 |
| Phone, Web, RS | 0,75 / 0,15 / 0,1 | × 0,85 |
| Phone, Web | 0,8 / 0,2 | × 0,80 |

> **Point d'attention** : toutes les combinaisons ci-dessus incluent le
> canal Phone. Si un participant a des tests comptabilisés sur une
> combinaison de canaux qui ne figure pas dans ce tableau (par exemple
> Mail seul, ou Phone absent), sa note finale consolidée n'est **pas
> calculable** : il n'est pas pris en compte pour désigner le gagnant de
> sa catégorie. Si ce n'est pas le comportement souhaité, précisez-moi la
> pondération à appliquer pour ces cas et j'ajuste.

**Liste des lauréats.** Version « cérémonie » de ce même calcul : pour
chaque catégorie ayant un gagnant calculable, affiche le trophée ESCDA,
le nom de la catégorie et le nom du participant lauréat — sans détail de
note, contrairement au tableau de la Liste des résultats.

Aucune migration de base de données n'est nécessaire pour cette étape : le
calcul se fait à la volée à partir des notes déjà calculées en
Compilation des résultats.

## Étape 10 — Sécurité et performance

Suite à un audit (sécurité des accès/de la base de données, et simulation
de charge à 50 participants × 200 tests), cinq correctifs ont été
apportés.

**1. Chargement fichier résultat 240x plus rapide.** La validation lisait
chaque cellule une par une ; passée à la méthode native d'openpyxl
(lecture par ligne), elle prenait **25 secondes pour 10 000 lignes contre
moins d'une seconde après correctif**, sans aucun changement de
comportement (mêmes erreurs détectées).

**2. Liste des tests : passage à un index léger.** À 10 000 tests, la
page embarquait un JSON complet par test et atteignait 44 Mo. Elle
affiche maintenant un index (participant, catégorie, nombre de tests) ;
le détail (avec les popups Code N / autres données) n'est chargé que pour
**un seul participant à la fois**, en cliquant sur son nom.

**3. Rôle Administrateur.** Jusqu'ici, n'importe quel utilisateur autorisé
avait accès à Administration et pouvait supprimer des données de test.
Un utilisateur est maintenant administrateur si son adresse figure dans
la nouvelle variable d'environnement `ADMIN_EMAILS`, ou si un
administrateur l'a promu depuis l'écran Administration (nouvelle section
« Administrateurs »). Seuls les administrateurs voient le menu
Administration et le bouton « Annuler un fichier » — et les routes
correspondantes sont bloquées (403) pour les autres, même en accès
direct.

> ⚠️ **Migration de base de données nécessaire** : cette étape ajoute une
> colonne à la table `user` existante sur Render. Avant de redéployer,
> connectez-vous à votre base PostgreSQL (Dashboard Render → `vcsoy-results-db`
> → **Connect**) et exécutez :
> ```sql
> ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;
> ```
> Définissez aussi `ADMIN_EMAILS` dans les variables d'environnement Render
> (Settings → Environment), avec au minimum votre propre adresse.

**4. Protection CSRF.** Tous les formulaires qui modifient des données
(les 13 de l'application) incluent maintenant un jeton anti-CSRF
(Flask-WTF) : une requête de modification forgée depuis un autre site,
au nom d'un utilisateur connecté, est désormais rejetée.

**5. Cookies de session durcis.** `SameSite=Lax`, durée de vie limitée à
8h, et — sur Render uniquement (`SESSION_COOKIE_SECURE=1`, déjà dans
`render.yaml`) — cookie transmis uniquement en HTTPS. Un `ProxyFix` a été
ajouté pour que Flask détecte correctement le HTTPS derrière le proxy de
Render (nécessaire pour que ce réglage fonctionne et pour l'URL de
callback Google).

> **Points restants, non traités ici** (décisions qui vous appartiennent) :
> - Le plan gratuit de la base PostgreSQL Render **expire après 90 jours
>   d'inactivité** — passez sur un plan payant avant cette échéance pour
>   éviter une perte de données.
> - Les plages de numéro de test (`validation.py`) totalisent 175
>   tests/participant au maximum (100+40+15+10+10) ; il faudra les élargir
>   pour atteindre les 200/participant visés.
> - Seules 2 éditions sont définies (`editions.py`) ; il en faudra
>   ajouter jusqu'à 5.

## Étape 10 bis — Correctif : suppression d'une catégorie/participant avec des tests

Supprimer une catégorie ou un participant ayant des tests chargés (ou une
catégorie ayant encore des participants) provoquait une erreur interne
(« Internal error ») et n'effectuait aucune suppression — les données
liées empêchaient la suppression au niveau de la base sans qu'un message
clair ne soit affiché.

Comportement corrigé :
- **Sans données liées** : suppression immédiate, comme avant.
- **Avec des tests (et/ou, pour une catégorie, des participants), pour un
  collaborateur standard** : suppression refusée avec un message clair
  indiquant combien de tests/participants sont concernés — rien n'est
  supprimé.
- **Avec des tests, pour un administrateur** : une confirmation explicite
  est demandée (encadré rouge indiquant précisément ce qui sera supprimé),
  avant de supprimer définitivement la catégorie/le participant **et**
  tous ses tests (et, pour une catégorie, ses participants).

Listes des tests, Compilation des résultats, Liste des résultats et Liste
des lauréats se recalculent à la volée à partir de la base à chaque
chargement de page : aucune action supplémentaire n'est nécessaire après
une suppression pour qu'ils reflètent la nouvelle situation.

Aucune migration de base de données n'est nécessaire pour ce correctif.

## Étape 11 — Éditions 2029/2030 et chargement d'une édition

**Nouveaux logos et éditions.** Ajout des logos ESCDA 2029 et 2030
(français et anglais, fond transparent) dans `app/static/img/`, et des
éditions correspondantes dans `editions.py` — l'outil gère maintenant 4
éditions (2027 à 2030). Les logos sont aussi reconnus par la Facturation
(`app/invoicing/generator.py`).

**Administration : « Charger une édition ».** Nouveau bouton qui copie
les **catégories et les participants** (jamais les tests) d'une édition
source vers une édition cible, pratique pour démarrer une nouvelle
édition sans tout ressaisir. L'opération est **sans risque à rejouer** :
une catégorie ou un participant déjà présent dans l'édition cible (même
code) n'est jamais dupliqué — seuls les éléments manquants sont copiés,
et le message de confirmation indique combien ont été ajoutés / déjà
présents.

Aucune migration de base de données n'est nécessaire pour cette étape.

## Étape 12 — Nouvel écran de connexion

La page de connexion démarre maintenant par une photo (célébration, trophée)
occupant une bonne partie du haut de la fenêtre, suivie de « Voted Customer
Service of The Year » (gros, gras, rouge) et « Outil de gestion des
résultats » (plus petit, gras, bleu marine). Le reste de l'écran (logos,
nom du projet VCSOY RESULTS, connexion Google/mode développement) est
inchangé, simplement repositionné en dessous.

Photo fournie convertie en JPEG optimisé (259 Ko au lieu de 2,3 Mo en PNG
d'origine) pour ne pas alourdir le chargement de la page.

Aucune migration de base de données n'est nécessaire pour cette étape.

## Étape 12 bis — Écran de connexion simplifié

« Outil de gestion des résultats » est maintenant plus gros (24px). Les
deux anciens logos ESCDA 2027, le titre « VCSOY RESULTS » et le sous-titre
« Outil de traitement des résultats — ESCDA Canada » ont été retirés de
l'écran de connexion, remplacés par le logo générique « Élu Service à la
Clientèle de l'Année » (sans année). La photo en haut de page occupe
également un peu plus de place (50vh au lieu de 42vh). Le reste de l'écran
(connexion Google/mode développement) est inchangé.

Aucune migration de base de données n'est nécessaire pour cette étape.

## Étape 13 — Chargement des records

Nouvel item de menu **« Chargement des records »**, qui permet de charger
en une fois un **lot de fichiers** (comme pour « Chargement fichier
résultat ») : un fichier **audio** pour un test Phone, un **PDF** pour les
autres canaux (Email, Web Navigation, Social Networks, Chat) — le
"record" étant la preuve/trace de chaque test mystère.

**Format de nom exigé** : chaque fichier doit être nommé exactement
`IDMYSTERYTEST-record.ext` (ex. `44031450-record.pdf`), où
`IDMYSTERYTEST` est la même chaîne de 8 chiffres CCPPXXXX utilisée pour
les résultats. Sont vérifiés avant tout enregistrement : le code
catégorie (CC), le code participant (PP) dans cette catégorie, que l'ID
Mystery Test correspond à un test **déjà chargé** dans « Chargement
fichier résultat » (sinon rejeté), et que l'extension correspond au canal
du test (audio pour Phone, PDF sinon). Comme pour les résultats, le
chargement est **tout-ou-rien** : si un seul fichier du lot est invalide,
rien n'est enregistré et la liste complète des erreurs est affichée.

Un fichier rechargé pour un ID Mystery Test déjà pourvu d'un record **le
remplace** plutôt que de créer un doublon.

**Stockage** : les records sont stockés directement en base de données
(nouvelle table `test_record`, colonne binaire), comme le reste des
données — pas sur le disque du serveur, qui est réinitialisé à chaque
déploiement Render. La limite de taille des requêtes a été augmentée à
300 Mo (`MAX_CONTENT_LENGTH`) pour permettre le chargement d'un lot de
fichiers audio en une seule fois.

Un bouton **« Ouvrir le record »** apparaît sur chaque test qui en a un,
dans « Liste des tests » (page de détail par participant), sur la page de
détail d'un test (recherche), et dans la popup de détail des tests d'un
participant sur « Compilation des résultats ».

Aucune migration de base de données n'est nécessaire : `test_record` est
une table entièrement nouvelle, créée automatiquement.

## Étape 13 bis — Ouverture des records + gestion de « Chargement des records »

Deux ajustements sur la fonctionnalité des records :

**Ouverture d'un record** : le bouton « Ouvrir le record » ouvre
maintenant le fichier différemment selon son type. Un **PDF** s'ouvre en
mode visionneuse dans un nouvel onglet (le fichier est servi en `inline`
plutôt qu'en pièce jointe forcée). Un fichier **audio** ouvre une popup
avec un lecteur (`<audio>` en lecture automatique) sans quitter la page.
Sur la page de détail d'un test (recherche), le bouton est désormais
positionné en haut, à côté du titre.

**« Chargement des records »** : la page n'affiche plus le tableau complet
des records chargés, mais un simple **compteur** (« N record(s) chargé(s)
pour cette édition »). Les administrateurs disposent en plus d'un bouton
**« Supprimer des records »**, qui ouvre une popup listant tous les
records avec une case à cocher par fichier ; la suppression exige de
cocher une case de confirmation et une seconde confirmation JavaScript, et
supprime définitivement les records sélectionnés de la base — le bouton
« Ouvrir le record » disparaît alors automatiquement partout où il
apparaissait pour ces tests (Liste des tests, détail d'un test,
Compilation des résultats).

## Étape 14 — Rapport d'études (écran initial)

Nouvel item de menu **« Rapport d'études »**. Cette première étape met en
place l'écran principal ; les fonctionnalités « Créer » et « Modifier »
seront définies et développées dans une prochaine étape (les boutons sont
déjà en place, mais affichent pour l'instant un message d'attente).

L'écran affiche le tableau des rapports d'études existants (case à
cocher, nom, date de création), avec en dessous les trois boutons
**« Créer »**, **« Modifier »** et **« Supprimer »** : « Modifier »
n'est actif que si **exactement un** rapport est coché, « Supprimer »
dès qu'**au moins un** l'est. La suppression (réservée aux
administrateurs, comme les autres suppressions définitives de
l'application) demande une confirmation avant d'effacer les rapports
sélectionnés.

Au-dessus du tableau, le bouton **« Charger un modèle de rapport »**
ouvre une popup reprenant le design de « Chargement fichier résultat » :
un simple champ de sélection de fichier (avec bouton « Choisir un
fichier ») et un bouton « Charger ». Le modèle est stocké directement en
base (nouvelle table `report_template`, colonne binaire), comme les
records de test — pas sur le disque du serveur.

## Étape 14 bis — Génération d'un rapport d'études (« Créer »)

Le bouton **« Créer »** ouvre désormais une popup demandant un **modèle**
(parmi ceux chargés) et un **participant**, avec un bouton « Créer » grisé
tant que les deux ne sont pas choisis (il devient rouge/actif dès que
c'est le cas), et un bouton « Annuler » à côté pour fermer sans rien
faire.

**Balises du modèle** : le modèle (.pptx) doit contenir des balises au
format `{{ Nom de la balise }}` (n'importe où : titre, zone de texte,
tableau). À la création, chaque balise est remplacée par la donnée
correspondante du participant choisi. Balises disponibles actuellement
(toutes déjà calculées ailleurs dans l'application, voir
`app/reports/report_data.py`) :

- `{{ Participant }}`, `{{ Code participant }}`, `{{ Catégorie }}`
- Pour chaque canal (Téléphone, Mail, WEB, RS, Chat) :
  `{{ Nb tests <canal> }}`, `{{ Note <canal> }}`
- `{{ Note consolidée }}`

Si le modèle contient une balise **non reconnue**, la création est
refusée avec un message listant précisément la ou les balises en cause
(rien n'est enregistré) — cela permet de vérifier un modèle avant de le
mettre à disposition des utilisateurs. D'autres balises (ex. temps moyen
de décroché pour Phone, nécessitant un nouveau calcul) seront ajoutées au
fur et à mesure des besoins.

Le rapport généré est stocké en base (comme les modèles), et un bouton
**« Télécharger »** est disponible sur chaque ligne du tableau. Une
visionneuse intégrée (pour prévisualiser le .pptx sans le télécharger)
reste à définir — voir la note de conception ci-dessous.

> **Note de conception (en attente d'arbitrage)** : afficher un .pptx
> directement dans le navigateur nécessite soit un service de visionneuse
> externe (Microsoft Office Online / Google Docs Viewer — mais cela
> implique d'envoyer le fichier, donc des données de résultats clients, à
> un tiers, via une URL temporaire accessible sans authentification),
> soit une conversion serveur (LibreOffice), qui demande de passer
> l'hébergement Render en environnement Docker. Aucune des deux options
> n'a été retenue pour l'instant ; à trancher avant d'implémenter la
> visionneuse.

## Étape 15 — Édition Blanche + édition de démarrage par utilisateur

Le titre affiché sur l'écran de connexion devient **« Outil de gestion
des Tests client Mystère »**.

Nouvelle édition **« Édition Blanche »**, un environnement de test qui
apparaît en premier dans toutes les listes d'édition (« Édition 0 »). Elle
réutilise le logo déjà présent `logo_annee_fr.png` (identique en français
et en anglais, y compris pour les factures).

Dans **Administration**, chaque utilisateur listé dispose désormais d'un
sélecteur **« Édition de démarrage »** : l'édition sur laquelle l'outil
s'ouvre à sa connexion. Par défaut (tant qu'elle n'a pas été changée),
c'est l'Édition Blanche. **Les administrateurs démarrent toujours sur
l'Édition Blanche**, quel que soit ce réglage — cela permet de continuer à
tester/simuler des données sans jamais perturber une édition réelle une
fois que celle-ci contient de vraies données.

**Important — migration de la base en production** : le modèle `User` a
une nouvelle colonne `default_edition_id`. Comme pour l'incident
précédent (table `study_report`), `db.create_all()` ne modifie jamais une
table déjà existante. Contrairement à `study_report`, la table `user`
contient de vraies données (comptes, droits admin) : il ne faut **surtout
pas** la supprimer. Il faut exécuter, une seule fois, sur la base de
production :

```sql
ALTER TABLE "user" ADD COLUMN default_edition_id VARCHAR(20);
```

## Étape 16 — Corrections diverses et compléments

**Correctifs :**
- **Case « Act Réf. » (Gestion des participants)** : la bascule ne
  fonctionnait plus depuis l'ajout de la protection CSRF (le fetch JS
  n'envoyait pas le jeton, la requête échouait silencieusement en 400).
  Corrigé.
- **Facturation** : un participant coché « Act Réf. » ne peut plus être
  sélectionné pour créer une facture (filtré dans la liste + contrôle
  serveur).
- **Suppression d'un participant/catégorie ou annulation d'un fichier de
  résultat** provoquait une erreur interne dès qu'un test possédait un
  record (`TestRecord`, clé étrangère non nulle vers `TestResult`) :
  les records sont désormais supprimés avant les tests. Les factures et
  rapports d'études déjà générés (instantanés autonomes) ne sont plus
  bloquants : leur référence au participant est simplement détachée
  (mise à `NULL`) plutôt que de provoquer une erreur ou d'être supprimés.

**Éditions :**
- L'**Édition Blanche** est désormais réservée aux administrateurs
  (masquée du sélecteur d'édition et de l'« édition de démarrage » pour
  les autres utilisateurs, avec contrôle serveur en complément). Un
  collaborateur sans édition de démarrage assignée démarre maintenant
  sur la première édition réelle (ESCDA 2027) plutôt que sur l'édition
  blanche.

**Rapport d'étude :**
- Le bouton **« Modifier »** devient **« Charger »** : permet de charger
  directement un fichier de rapport déjà prêt (.pptx) depuis le disque
  local, qui apparaît alors dans la liste des rapports d'étude (sans
  passer par un modèle ni des balises).
- La liste des rapports d'étude affiche désormais l'**heure** en plus de
  la date de création.

**Gestion des participants :**
- Les en-têtes **« Category Name »** et **« Code »** sont cliquables et
  trient la liste par ordre croissant (même principe que le tri déjà en
  place sur Compilation des résultats).

## Étape 17 — Liste des résultats/lauréats en % + moyennes dans les popups

Dans « Liste des résultats », seule la colonne **« Note consolidée »**
du tableau principal (et la colonne **« Note finale »** du tableau des
gagnants en dessous) s'affiche désormais en base 100 avec un signe `%`,
au lieu de la note sur 20 — toutes les autres notes (par canal) restent
sur 20. « Liste des lauréats » affiche la note finale en % à côté du nom
du lauréat. Les popups **« Résultats par canal par catégorie »** et
**« toutes catégories »** affichent la moyenne des participants (sur 20)
au-dessus de la liste.

## Étape 18 — Gestion des scénarios : Générer des scénarios

Deux sous-fonctionnalités apparaissent dans le menu, indentées, sous
« Gestion des scénarios » (visibles uniquement quand on est dans cette
section) : **« Générer des scénarios »** (détaillée ci-dessous) et
**« Générer les tests »** (écran d'attente, sera défini dans une
prochaine étape).

« Générer des scénarios » reprend la structure de « Rapport d'étude » :

- **Modèles de scénarios chargés** : table listant les modèles de
  **Book scénario** et de **Problématiques** (fichier, type, date de
  chargement), avec deux boutons de chargement dédiés (« Charger modèle
  Book scénario » / « Charger modèle Problématiques », même design que
  « Chargement fichier résultat », aucune restriction de format). Un
  bouton **« Supprimer un modèle »** (admin, popup à cases à cocher,
  confirmation) permet de retirer un modèle ; si un fichier scénario déjà
  généré en dépendait, sa référence est détachée (mise à `NULL`) plutôt
  que bloquée.
- **Fichiers scénarios** : table des fichiers générés/chargés (nom, date
  et heure de création, bouton Télécharger), avec trois boutons :
  - **Générer un book** : vérifie qu'au moins un modèle de chaque type
    existe, sinon invite à en charger un ; sinon ouvre une popup pour
    choisir un modèle de Book, un modèle de Problématiques, un participant
    et l'URL de son site web. Voir Étape 19 pour la génération réelle.
  - **Charger** : charge directement un fichier scénario déjà prêt depuis
    le disque local.
  - **Supprimer** (admin, sélection + confirmation) : supprime les
    fichiers scénarios sélectionnés.

## Étape 19 — Génération de scénarios par IA (Claude Sonnet 5)

Le bouton **« Générer un book »** génère désormais du contenu réel plutôt
qu'une simple copie de modèle.

- **Popup** : en plus des sélections de modèles et du participant, un
  champ obligatoire demande l'**URL du site web du participant** (saisie à
  chaque génération, non enregistrée sur la fiche participant).
- **Fichiers idempotents** : à la génération, si les fichiers
  `Book_scénario_<Participant>_<Édition>` et
  `Problématiques_<Participant>_<Édition>` existent déjà pour ce
  participant, ils sont **réutilisés et enrichis** plutôt que recréés (les
  scénarios déjà validés par l'utilisateur sont conservés).
- **Génération IA (Claude Sonnet 5, avec recherche web)** : le modèle
  recherche sur le vrai site du participant (FAQ, informations générales),
  s'inspire des problématiques listées sur la diapositive 2 du fichier
  Problématiques, et apprend des scénarios déjà validés (colonne A = 1)
  dans le Book pour générer **10 nouveaux scénarios** par clic.
- **Book scénario (Excel, feuille « step 1 »)** : chaque nouveau scénario
  remplit les colonnes A (validation, à 0), B (Entreprise), C (numéro,
  incrémenté), D (Prospect/Client), E (contexte), F (question), G
  (réponse). Les colonnes H à K et la feuille « Recap » ne sont jamais
  touchées ; les lignes déjà validées (A = 1) ne sont jamais modifiées et
  servent d'exemples pour les générations suivantes.
- **Problématiques (PowerPoint)** : une diapositive est ajoutée par
  scénario généré, indiquant son numéro et l'URL où l'information a été
  trouvée (pas de capture d'écran).
- Nécessite la variable d'environnement `ANTHROPIC_API_KEY` (voir
  `.env.example`) ; en son absence, un message d'erreur explicite s'affiche
  sans créer de fichier partiel. La génération peut prendre plusieurs
  minutes (recherche web réelle) : timeout gunicorn et client Anthropic
  réglés à 600 s en conséquence.
- **Charger** un fichier scénario propose maintenant un champ
  **Participant (optionnel)** : si le fichier rechargé remplace le Book
  scénario ou les Problématiques d'un participant (par exemple après
  validation/nettoyage manuel des scénarios en dehors de l'outil), le lier
  au participant lui donne le nom attendu par « Générer un book », pour
  que la prochaine génération continue à partir de ce fichier au lieu
  d'en recréer un depuis le modèle. Recharger pour le même participant met
  à jour le fichier existant plutôt que d'en créer un doublon.
- « Générer les tests » (qui dupliquera les scénarios validés selon la
  colonne K, pour générer par exemple des tests téléphoniques) reste à
  spécifier dans une prochaine étape.

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
│   │   ├── routes.py              # Chargement de fichier + Listes des tests + recherche + Compilation
│   │   ├── validation.py          # Règles de contrôle du fichier Excel
│   │   ├── presentation.py        # Extraction Code N / observation / autres données
│   │   └── scoring.py             # Calcul des notes (Compilation, Liste des résultats, Lauréats)
│   ├── records/
│   │   ├── routes.py              # Chargement des records + téléchargement
│   │   └── validation.py          # Règles de contrôle des fichiers record
│   ├── reports/
│   │   └── routes.py              # Rapport d'études : liste, modèle, suppression
│   ├── scenarios/
│   │   ├── routes.py              # Générer des scénarios : modèles, création, génération IA
│   │   ├── ai_generation.py       # Appel Claude Sonnet 5 (recherche web + génération)
│   │   ├── excel_utils.py         # Lecture/écriture du Book scénario (feuille "step 1")
│   │   └── pptx_utils.py          # Lecture/écriture du fichier Problématiques
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

Toutes les fonctionnalités du menu ont maintenant une implémentation
(compilation des résultats, présentation des résultats, lauréats,
facturation, administration). Prochaines évolutions au fur et à mesure de
vos indications.
