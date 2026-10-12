# Traitements — NewsIA

Pipeline complet de récupération, analyse et résumé d'articles de presse.

---

## Vue d'ensemble du pipeline

```
Flux RSS
    ↓
Phase 1 — Récupération titres RSS en parallèle (sans téléchargement contenu)
    ↓
Clustering HDBSCAN sur les titres (en mémoire)
    Sauvegarde embedding_titre en BDD au passage
    ↓
Analyse GPT — sélection des clusters importants + génération questions RAG
    ↓
Phase 2 — Téléchargement contenu uniquement des articles sélectionnés (~25%)
           Embedding Voyage 4 + stockage BDD
    ↓
Phase 3 — Recherche vectorielle pgvector (RAG)
           Enregistrement cluster + liaisons articles
           Résumé final GPT
           Sauvegarde résumés avec FK vers clusters
```

---

## Structure des fichiers

```
NewsIA/
├── docker-compose.yml
├── .env
├── .env.example
├── docs/
│   └── api.md
├── api/
│   ├── Dockerfile
│   └── serveur.js
├── traitements/
│   ├── Dockerfile
│   ├── crontab
│   ├── entrypoint.sh
│   ├── requirements.txt
│   ├── bdd/
│   │   ├── connexion.py
│   │   ├── communs.py
│   │   ├── enregistrementArticle.py
│   │   ├── enregistrementCluster.py
│   │   ├── enregistrementResumes.py
│   │   └── rechercheVectorielle.py
│   ├── rss/
│   │   ├── fluxRSS.json
│   │   ├── rss.py
│   │   └── collecte.py
│   ├── clustering/
│   │   └── hdbscan.py
│   ├── llm/
│   │   ├── analyseCluster.py
│   │   └── resumeFinal.py
│   ├── rag/
│   │   └── generationRequete.py
│   ├── config/
│   │   ├── prompts.py
│   │   └── interets.py
│   └── main.py
```

---

## Détail de chaque fichier

### `bdd/connexion.py`

Point d'entrée unique vers la base de données PostgreSQL.
Lit `BDD_URL` depuis `.env` et expose `get_connection()`.
Importé par tous les fichiers qui ont besoin d'accéder à la BDD.

### `bdd/communs.py`

Fonctions partagées d'embedding utilisées par tout le projet.
Évite la duplication entre `enregistrementArticle.py` et `generationRequete.py`.

Expose :

- `generer_embedding(texte)` — embed un seul texte
- `embedder_textes(texts)` — embed une liste avec batching automatique
- `count_tokens(text)` — approximation du nombre de tokens (~4 chars/token, sans dépendance externe)
- `dispatch_batches(texts)` — découpe en batches d'indices respectant 32K tokens max

### `bdd/enregistrementArticle.py`

Met à jour les articles en BDD avec leur contenu et leur embedding complet (titre + contenu).
Utilise `embedder_textes()` depuis `communs.py` pour générer tous les embeddings en un minimum de requêtes.
Opère via `UPDATE … WHERE url = …` — les articles sont insérés sans contenu par `collecte.py` en amont.

**Entrée :** `list[dict]` — chaque dict `{ titre, url, contenu, source }`
**Sortie :** `list[int]` — ids des articles mis à jour

### `bdd/enregistrementCluster.py`

Insère un cluster en BDD et crée les liaisons avec ses articles sources dans `cluster_articles`.
Appelé dans `resumeFinal.py` juste avant l'appel GPT, afin que le `cluster_id` soit disponible pour le résumé.

**Entrée :** `topic_id: str`, `titre: str`, `articles: list[dict]` (doivent avoir un champ `id`)
**Sortie :** `int | None` — id du cluster inséré, ou `None` en cas d'erreur

### `bdd/enregistrementResumes.py`

Sauvegarde les résumés en BDD avec leur FK vers la table `clusters`.

**Entrée :** `list[dict]` — chaque dict `{ cluster_id, titre, resume, cluster_id_fk }`

### `bdd/rechercheVectorielle.py`

Recherche les articles les plus proches sémantiquement dans pgvector.
Prend un vecteur (embedding d'une question RAG) et retourne les top K articles similaires triés par score de similarité cosinus.

**Entrée :** `embedding: list[float]`
**Sortie :** `list[dict]` — articles avec score de similarité

---

### `rss/fluxRSS.json`

Liste des flux RSS à surveiller, organisés par catégorie (technologies, géopolitique, IA, cybersécurité, france, finances).

### `rss/collecte.py`

Script autonome déclenché toutes les 3h par le CRON.
Parse tous les flux RSS et insère les articles (titre, url, source) en BDD sans télécharger le contenu.
Les articles sont insérés avec `contenu = NULL` et `embedding = NULL` — ils seront complétés par `main.py`.

L'article « à la une » de ZoneBourse n'est gardé que s'il a été publié le jour même (balise
`article:published_time` de la page). Le matin, le week-end ou un jour férié, la une est encore l'article
de la veille au soir, qui se retrouvait sinon dans le résumé du jour.

### `rss/rss.py`

Expose deux fonctions publiques correspondant aux deux premières phases du pipeline.
Toute la logique de scraping (stealth, Playwright headless, proxies paywall, stats par domaine) est interne.

**`recuperer_articles_du_jour()` — Phase 1**
Parse tous les flux RSS en parallèle via `ThreadPoolExecutor`.
Retourne les articles du jour sous forme de `list[dict]` `{ titre, lien, source, description }`.
Aucun contenu n'est téléchargé à ce stade.

**`telecharger_et_enregistrer(articles, urls_selectionnees)` — Phase 2**
Télécharge en parallèle uniquement les articles dont l'URL est dans `urls_selectionnees`.
Cascade de téléchargement pour chaque article : HTTP discret → Playwright → proxies (12ft, archive.ph) → résumé RSS.
Appelle `ajouter_articles_batch()` pour l'embedding et la mise à jour BDD en une seule passe.
Affiche un rapport par domaine (taux de succès, erreurs) à la fin.

---

### `clustering/hdbscan.py`

Clusturise les articles du jour sur leurs **titres uniquement**.
Sauvegarde les embeddings de titres dans la colonne `embedding_titre` de la table `articles` au passage.

**Pourquoi sur les titres ?**
Permet de sélectionner les sujets importants _avant_ de télécharger le contenu,
ce qui réduit le volume de scraping à ~25% des articles et accélère fortement le pipeline.

**Étapes internes :**

1. Embed les titres via `embedder_textes()` depuis `communs.py`
2. Sauvegarde les embeddings de titres en BDD via `_sauvegarder_embeddings_titres()`
3. Lance HDBSCAN (`min_cluster_size=4`, `cluster_selection_method="leaf"`)
4. Ignore le bruit (label `-1`) — comportement intentionnel de HDBSCAN

**Entrée :** `list[dict]` — articles RSS avec leur titre
**Sortie :** `dict[int, list[dict]]` — `{ cluster_id: [article, ...] }` sans le cluster `-1`

---

### `llm/analyseCluster.py`

Envoie les clusters à GPT pour sélection et génération de questions RAG.
Modèle utilisé ici et dans `resumeFinal.py` : `gpt-6-luna` (alias déclaré dans `../commun/litellm/config.yaml`).
Formate les titres par cluster en YAML avant envoi.

**Entrée :** `dict[int, list[dict]]` — clusters de `hdbscan.py`

**GPT retourne (JSON structuré) :**

- `id` — identifiant unique du topic
- `title` — titre journalistique du cluster
- `cluster_ids` — identifiants HDBSCAN fusionnés dans ce topic
- `questions` — 6 à 10 questions RAG indépendantes sur le sujet
- `importance_order` — ordre d'importance des topics sélectionnés

**Règles GPT :** sélectionne 8 à 12 topics, ignore les sujets sportifs ou trop niche, perspective éditoriale TV. Regroupe tous les sujets financiers en un seul topic "Tour d'horizon des marchés financiers".

---

### `rag/generationRequete.py`

Orchestre la recherche vectorielle pour chaque topic.
Utilise `generer_embedding()` depuis `communs.py`.

**Pour chaque topic :**

1. Génère un embedding Voyage 4 pour chacune des questions RAG
2. Recherche les top 10 articles similaires via `rechercheVectorielle.py`
3. Dédoublonne les résultats sur l'ensemble des questions du topic
4. Trie par score de similarité décroissant

**Sortie :** `list[dict]` — un dict par topic avec `cluster_id`, `titre`, `questions`, `articles`
Respecte l'ordre d'importance défini par GPT dans `analyseCluster.py`.

---

### `llm/resumeFinal.py`

Génère un résumé en français pour chaque cluster à partir des articles RAG.
Enregistre le cluster et ses liaisons articles avant chaque appel GPT.

**Entrée :** résultats RAG de `generationRequete.py`
**Contexte envoyé à GPT :** tous les articles RAG du cluster concaténés

**Pour chaque cluster :**

1. Appelle `enregistrer_cluster()` → insère dans `clusters` + `cluster_articles`, récupère le `cluster_id_fk`
2. Appelle GPT → résumé 100-180 mots en français
3. Retourne `{ cluster_id, titre, resume, cluster_id_fk }`

**GPT produit :** texte brut en français, 100-180 mots, structuré en trois parties (faits → contexte → perspectives), sans mise en forme ni mention des sources.

**Sortie :** `list[dict]` — `{ cluster_id, titre, resume, cluster_id_fk }` dans l'ordre d'importance

---

## Variables d'environnement (`.env`)

| Variable            | Description                                                                               |
| ------------------- | ----------------------------------------------------------------------------------------- |
| `BDD_URL`           | URL de connexion vers la base `projets` du Postgres commun (host = `postgres`)            |
| `LITELLM_PROXY_URL` | URL du proxy LiteLLM commun, via le réseau Docker `commun` : `http://litellm:4000`        |
| `LITELLM_API_KEY`   | Clé API du proxy LiteLLM (`master_key` de `../commun/litellm/config.yaml`)                |
| `PORT_EXPRESS`      | Port d'écoute de l'API (`8100`)                                                           |

`BDD_URL` doit toujours utiliser `postgres` comme host (le nom du service dans `../commun/docker-compose.yml`),
jamais `localhost` ni une IP. Les variables de Postgres et les clés OpenAI / Voyage sont dans `../commun/.env`.

---

## Base de données

### Table `articles` (PostgreSQL + pgvector)

| Colonne           | Type           | Description                           |
| ----------------- | -------------- | ------------------------------------- |
| `id`              | `SERIAL`       | Clé primaire                          |
| `titre`           | `TEXT`         | Titre de l'article                    |
| `url`             | `TEXT UNIQUE`  | URL source (contrainte d'unicité)     |
| `contenu`         | `TEXT`         | Contenu extrait par newspaper4k       |
| `source`          | `TEXT`         | Nom du flux RSS source                |
| `date_ajout`      | `TIMESTAMP`    | Date d'insertion                      |
| `embedding`       | `vector(1024)` | Embedding Voyage 4 du titre + contenu |
| `embedding_titre` | `vector(1024)` | Embedding Voyage 4 du titre seul      |

Index : HNSW sur `embedding`, btree sur `source` et `date_ajout`.

### Table `clusters`

| Colonne    | Type        | Description                                |
| ---------- | ----------- | ------------------------------------------ |
| `id`       | `SERIAL`    | Clé primaire                               |
| `topic_id` | `TEXT`      | Identifiant GPT du topic (ex: "1", "2", …) |
| `titre`    | `TEXT`      | Titre journalistique généré par GPT        |
| `date_run` | `TIMESTAMP` | Date d'insertion (horodatage du run)       |

### Table `cluster_articles` (table de liaison)

| Colonne      | Type      | Description         |
| ------------ | --------- | ------------------- |
| `cluster_id` | `INTEGER` | FK → `clusters(id)` |
| `article_id` | `INTEGER` | FK → `articles(id)` |

Clé primaire composite `(cluster_id, article_id)`. Cascade sur suppression du cluster.

### Table `resumes`

| Colonne         | Type      | Description              |
| --------------- | --------- | ------------------------ |
| `id`            | `SERIAL`  | Clé primaire             |
| `cluster_id`    | `TEXT`    | Identifiant GPT du topic |
| `titre`         | `TEXT`    | Titre du cluster         |
| `resume`        | `TEXT`    | Résumé généré par GPT    |
| `cluster_id_fk` | `INTEGER` | FK → `clusters(id)`      |
| `prix`          | `DOUBLE PRECISION` | Coût en dollars des appels GPT du résumé (voir plus bas) |
| `nb_articles_rss` | `INTEGER` | Nombre d'articles RSS collectés sur 24 h ayant servi au run (même valeur pour tous les résumés du run) |

`prix` vient de l'en-tête `x-litellm-response-cost` renvoyé par LiteLLM. Il contient l'appel GPT de rédaction
plus une part égale de l'appel GPT de choix des clusters, si bien que la somme des `prix` d'une journée donne
son coût GPT réel. Les embeddings Voyage ne sont pas comptés (quota gratuit), même si LiteLLM leur attribue
un coût dans ses propres statistiques. La colonne a été ajoutée le 04/10/2026 (`ALTER TABLE resumes ADD COLUMN prix
double precision`) ; les résumés antérieurs ont `prix = NULL`.

`nb_articles_rss` a été ajoutée le 07/10/2026 (`ALTER TABLE resumes ADD COLUMN nb_articles_rss integer`). Elle est
enregistrée pendant le traitement car les articles non retenus sont supprimés à la fin du run.

### Table `collectes`

Une ligne par passage de `collecte.py` (toutes les 3 h). Contrairement à `articles`, elle n'est jamais nettoyée :
c'est elle qui permet de savoir combien d'articles ont été récupérés au fil d'une journée.

| Colonne            | Type        | Description |
| ------------------ | ----------- | ----------- |
| `id`               | `SERIAL`    | Clé primaire |
| `date_collecte`    | `TIMESTAMP` | Heure de la collecte (UTC), index btree |
| `nb_articles_flux` | `INTEGER`   | Articles du jour renvoyés par les flux à ce passage (doublons d'un passage à l'autre compris) |
| `nb_nouveaux`      | `INTEGER`   | Articles réellement ajoutés en base à ce passage |

Créée le 08/10/2026 :

```sql
CREATE TABLE collectes (
    id SERIAL PRIMARY KEY,
    date_collecte TIMESTAMP NOT NULL DEFAULT now(),
    nb_articles_flux INTEGER NOT NULL,
    nb_nouveaux INTEGER NOT NULL
);
CREATE INDEX collectes_date_collecte_idx ON collectes (date_collecte);
```

L'API expose ce suivi : `GET /collectes/:date` (détail dans [`docs/api.md`](docs/api.md)).

L'API renvoie ces deux champs : `GET /resumes/:date` → `{ date, nbArticlesRecuperes, resumes: [{ titre, resume, prix, sources }] }`.
Détail de la réponse : [`docs/api.md`](docs/api.md).

---

## Requête API type — sources d'un résumé

```sql
SELECT a.titre, a.url, a.source
FROM cluster_articles ca
JOIN articles a ON a.id = ca.article_id
WHERE ca.cluster_id = $1
```

---

## Déploiement Docker

Le projet a 2 conteneurs, orchestrés par `docker-compose.yml` à la racine du projet. Postgres et LiteLLM
sont des ressources partagées entre projets, dans `../commun` (voir son `README.md`) : il faut les démarrer
avant NewsIA.

| Conteneur          | Rôle                                                                     | Port(s)                        |
| ------------------ | ------------------------------------------------------------------------ | ------------------------------ |
| `commun-postgres`  | PostgreSQL 17 + `pgvector` (dans `../commun`), base `projets`            | `5432`                         |
| `commun-litellm`   | Proxy LiteLLM (dans `../commun`) : `gpt-6-luna` et embeddings Voyage     | `4000`                         |
| `news-api`         | API Node.js (`serveur.js`), lit les données pour le front                | `8100`                         |
| `news-traitements` | Cron (Python + Playwright + xvfb) qui exécute `collecte.py` et `main.py` | _(aucun, pas de serveur HTTP)_ |

Chaque service est construit à partir de son propre `Dockerfile` (`api/Dockerfile`,
`traitements/Dockerfile`). `api` et `traitements` rejoignent le réseau Docker externe `commun`, créé par
`../commun/docker-compose.yml`, et joignent Postgres et LiteLLM par leur nom de service (`postgres`,
`litellm`), jamais `localhost` ni une IP.

### Cron intégré au conteneur `traitements`

Un vrai `cron` (crond) tourne à l'intérieur du conteneur `news-traitements`, avec cette
planification (`traitements/crontab`, fuseau `Europe/Paris`) :

| Horaire                                                                | Commande                                         |
| ---------------------------------------------------------------------- | ------------------------------------------------ |
| `00:01`, `03:01`, `06:01`, `09:01`, `12:01`, `15:01`, `18:01`, `21:01` | `xvfb-run -a python -m traitements.rss.collecte` |
| `23:50`                                                                | `python -m traitements.main`                     |

Mémoire : le conteneur est limité à 1 Go. Le pic vient des téléchargements Playwright de `main.py` ;
`rss.py` n'ouvre qu'un Chromium à la fois, le referme après chaque page et bloque images, vidéos et polices.
Ne pas augmenter le nombre de navigateurs simultanés sans remesurer : 5 Chromium ouverts en parallèle
ont fait tuer le traitement par l'OOM killer les 07/10 et 08/10/2026.

Les logs des jobs sont redirigés vers `/var/log/cron.log` dans le conteneur, et remontent dans
`docker logs news-traitements` grâce à l'entrypoint (`tail -f`).

Format des logs (module `traitements/journal.py`) : une ligne par étape, `[jj/mm hh:mm:ss] message`.
Une collecte tient en une ligne, un traitement en une quinzaine (clustering, sujets retenus, une ligne par
résumé avec son coût, total de la journée). Les étapes détaillées du scraping ZoneBourse sont en niveau
`DEBUG` (masquées) ; les avertissements et erreurs restent affichés.

### Démarrer / arrêter le stack

```bash
# Prérequis : les ressources communes tournent (cd ../commun && docker compose up -d)
# Depuis la racine du projet (là où se trouve docker-compose.yml)
docker compose up -d --build      # démarre api et traitements, en arrière-plan
docker compose ps                 # état des 2 conteneurs
docker compose down               # arrête NewsIA (la base, dans ../commun, n'est pas touchée)
```

### Suivre les logs

```bash
docker logs -f news-traitements   # cron + sorties de collecte.py / main.py
docker logs -f news-api           # API Node.js
docker logs -f commun-litellm     # proxy LiteLLM
docker logs -f commun-postgres    # Postgres
```

### Lancer une tâche à la main (sans attendre le cron)

Le conteneur `traitements` doit déjà être démarré (`docker compose up -d`). On y exécute alors
la commande directement, comme le ferait le cron :

**Collecte RSS (`collecte.py`) — en interactif, pour voir les logs en direct :**

```bash
docker exec -it news-traitements bash -c "cd /app && xvfb-run -a python -m traitements.rss.collecte"
```

⚠️ En mode interactif (`-it`), un `Ctrl+C` interrompt réellement le script (utile pour tester,
risqué si tu veux le laisser aller au bout).

**Collecte RSS — en arrière-plan, pour la laisser tourner sans risque d'interruption :**

```bash
docker exec -d news-traitements bash -c "cd /app && xvfb-run -a python -m traitements.rss.collecte >> /var/log/cron.log 2>&1"
docker logs -f news-traitements   # suit la progression ; Ctrl+C ici arrête juste le suivi, pas le script
```

**Traitement complet (`main.py`) — clustering, RAG, résumés :**

```bash
docker exec -it news-traitements bash -c "cd /app && python -m traitements.main"
```

_(pas besoin de `xvfb-run` ici : `main.py` ne fait pas de scraping Playwright, contrairement à
`collecte.py` qui en a besoin pour ZoneBourse)_

### Ouvrir un shell dans un conteneur (debug)

```bash
docker exec -it news-traitements bash
docker exec -it commun-postgres psql -U <user> -d projets
```

### Reconstruire après une modification du code

```bash
# Après avoir modifié traitements/*.py :
docker compose up -d --build traitements

# Après avoir modifié api/*.js :
docker compose up -d --build api
```

`--build` ne reconstruit que si des fichiers ont changé (cache Docker), donc pas besoin de
s'inquiéter du temps de build à chaque petite modif.

---

## Application mobile — React Native

Une app **React Native** consomme l'API (`news-api`, port `8100`) pour permettre la lecture des
résumés et des sources sur mobile.

<img src="./apercu_app.jpg" alt="Screenshot de l'app NewsIA" width="300">

⚠️ Non fourni dans le dépôt

## Historique — lancement sans Docker (déprécié)

Avant la dockerisation, le pipeline était lancé directement sur l'hôte via deux scripts CRON
système. Conservé ici à titre indicatif — **ne plus utiliser en production**, tout passe
désormais par `docker exec` sur le conteneur `traitements` (voir section Docker ci-dessus).

```bash
# Ancienne collecte RSS
cd traitements && source venv/bin/activate && cd ..
xvfb-run -a python -m traitements.rss.collecte

# Ancien traitement complet
cd traitements && source venv/bin/activate && cd ..
python -m traitements.main
```
