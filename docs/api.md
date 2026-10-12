# API NewsIA

Service `news-api` (Node.js + Express, `api/serveur.js`), port `8100`. Deux routes : `GET /resumes/:date` et
`GET /collectes/:date`. L'API ne fait que lire la base :
les résumés sont produits chaque soir à 23 h 50 par `traitements/main.py`.

## `GET /resumes/:date`

Renvoie les résumés générés pour une journée.

### Paramètre

| Paramètre | Format       | Exemple      | Description                                      |
| --------- | ------------ | ------------ | ------------------------------------------------ |
| `date`    | `AAAA-MM-JJ` | `2026-10-06` | Jour de génération des résumés (en heure UTC) |

Le filtre porte sur `date_resume`, de `00:00:00` à `23:59:59` UTC. Le traitement tourne à 23 h 50 heure de
Paris, soit 21 h 50 ou 22 h 50 UTC : les résumés d'un soir sont donc bien rattachés à ce jour-là.

### Exemple

```bash
curl http://192.168.1.31:8100/resumes/2026-10-06
```

```json
{
  "date": "2026-10-06",
  "nbArticlesRecuperes": 742,
  "resumes": [
    {
      "titre": "Tour d'horizon des marchés financiers",
      "resume": "Les marchés européens ont terminé la séance en hausse...",
      "prix": 0.00042,
      "sources": [
        { "lienArticle": "https://exemple.fr/article-1", "nom": "Le CAC 40 termine en hausse" },
        { "lienArticle": "https://exemple.fr/article-2", "nom": "La BCE maintient ses taux" }
      ]
    }
  ]
}
```

### Champs de la réponse

| Champ                   | Type             | Description |
| ----------------------- | ---------------- | ----------- |
| `date`                  | `string`         | La date demandée, renvoyée telle quelle. |
| `nbArticlesRecuperes`   | `number \| null` | Nombre d'articles RSS collectés sur les 24 h précédant le traitement et utilisés pour générer les résumés du jour (clustering puis sélection par GPT). `null` si aucun résumé ce jour-là, ou pour les résumés antérieurs au 07/10/2026 (valeur pas encore enregistrée). |
| `resumes`               | `array`          | Les résumés du jour, du plus récent au plus ancien. Tableau vide si rien n'a été généré. |
| `resumes[].titre`       | `string`         | Titre du sujet, rédigé par GPT. |
| `resumes[].resume`      | `string`         | Résumé en français, 100 à 180 mots, texte brut sans mise en forme. |
| `resumes[].prix`        | `number \| null` | Coût en dollars des appels GPT de ce résumé (rédaction plus une part de l'appel de choix des sujets). La somme des `prix` d'une journée donne son coût GPT total. `null` avant le 04/10/2026. |
| `resumes[].sources`     | `array`          | Articles qui ont servi à écrire le résumé. |
| `resumes[].sources[].lienArticle` | `string` | URL de l'article d'origine. |
| `resumes[].sources[].nom`         | `string` | Titre de l'article d'origine. |

`nbArticlesRecuperes` compte tout ce qui a été collecté, pas seulement les articles retenus. Le nombre
d'articles réellement utilisés par un résumé est `resumes[].sources.length`. Les articles non retenus sont
supprimés de la base à la fin du traitement : c'est pour ça que ce nombre est enregistré au moment de la
génération (colonne `resumes.nb_articles_rss`) au lieu d'être recompté par l'API.

### Erreurs

| Code  | Corps                    | Cas |
| ----- | ------------------------ | --- |
| `500` | `{ "error": "message" }` | Erreur base de données, ou date mal formée. |

### Historique du format

Avant le 07/10/2026, la route renvoyait directement le tableau des résumés (`[{ titre, resume, prix, sources }]`).
Elle renvoie maintenant un objet : les clients doivent lire `reponse.resumes`.

## `GET /collectes/:date`

Renvoie le nombre d'articles récupérés au fil d'une journée, une entrée par passage du cron de collecte
(00 h 01, 03 h 01, puis toutes les 3 h jusqu'à 21 h 01). Appelée en cours de journée, elle renvoie les
collectes déjà faites : c'est le compteur « en direct ».

### Paramètre

| Paramètre | Format       | Exemple      | Description |
| --------- | ------------ | ------------ | ----------- |
| `date`    | `AAAA-MM-JJ` | `2026-10-09` | Journée en heure de Paris (de 00:00 à 23:59, heure française). |

Contrairement à `/resumes/:date`, le découpage se fait en heure de Paris : la collecte de 00 h 01 est
bien comptée dans sa journée, alors qu'en UTC elle tomberait la veille.

### Exemple

```bash
curl http://192.168.1.31:8100/collectes/2026-10-09
```

```json
{
  "date": "2026-10-09",
  "nbArticlesRecuperes": 297,
  "nbCollectes": 3,
  "collectes": [
    { "heure": "00:01", "nbArticlesFlux": 180, "nbNouveaux": 180, "cumul": 180 },
    { "heure": "03:01", "nbArticlesFlux": 195, "nbNouveaux": 22,  "cumul": 202 },
    { "heure": "06:01", "nbArticlesFlux": 260, "nbNouveaux": 95,  "cumul": 297 }
  ]
}
```

### Champs de la réponse

| Champ                        | Type     | Description |
| ---------------------------- | -------- | ----------- |
| `date`                       | `string` | La date demandée. |
| `nbArticlesRecuperes`        | `number` | Total des nouveaux articles ajoutés en base sur la journée (somme des `nbNouveaux`). `0` si aucune collecte. |
| `nbCollectes`                | `number` | Nombre de passages du cron enregistrés ce jour-là (8 sur une journée complète). |
| `collectes`                  | `array`  | Les passages, du plus ancien au plus récent. |
| `collectes[].heure`          | `string` | Heure du passage, `HH:MM`, heure de Paris. |
| `collectes[].nbArticlesFlux` | `number` | Articles du jour présents dans les flux RSS à ce passage. Un même article apparaît souvent à plusieurs passages, ces valeurs ne s'additionnent donc pas. |
| `collectes[].nbNouveaux`     | `number` | Articles qui n'étaient pas encore en base, donc réellement récupérés à ce passage. |
| `collectes[].cumul`          | `number` | Total des `nbNouveaux` depuis le début de la journée, ce passage compris. |

`nbArticlesRecuperes` de cette route et celui de `/resumes/:date` ne mesurent pas la même chose :
ici, ce sont les articles d'une journée calendaire (minuit à minuit), là-bas, ceux des 24 h qui précèdent
le traitement de 23 h 50 et qui ont servi aux résumés.

Le suivi a commencé le 08/10/2026 : les jours précédents renvoient `nbCollectes: 0`.

### Erreurs

| Code  | Corps                    | Cas |
| ----- | ------------------------ | --- |
| `400` | `{ "error": "Date attendue au format AAAA-MM-JJ" }` | Date mal formée. |
| `500` | `{ "error": "message" }` | Erreur base de données. |
