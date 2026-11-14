"""
Résumé de la semaine, le dimanche à 23h50 : condense les résumés quotidiens des 7 derniers jours.

Ne fait rien (sans erreur) s'il y a moins de MIN_JOURS jours de résumés, par exemple
après une semaine sans traitement. Le résumé hebdo est enregistré comme un résumé
ordinaire (cluster_id 0, sans article source) : l'API l'affiche à la date du dimanche.

    python -m traitements.hebdo
"""
import time

import requests

from traitements.bdd.connexion import get_connection
from traitements.bdd.enregistrementResumes import enregistrement_resumes
from traitements.journal import log
from traitements.llm.client import appeler_chat
from traitements.notification import envoyer_notification

MODEL = "gpt-6-luna"
EFFORTS = "low"
CLUSTER_HEBDO = 0   # cluster_id des résumés hebdo, écartés de l'historique du traitement quotidien
MIN_JOURS = 2       # nombre minimal de jours avec résumés pour faire une synthèse

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

INSTRUCTION = """Tu es un journaliste de télévision francophone expert en synthèse d'actualité.
On te donne les résumés publiés chaque jour de la semaine. Tu rédiges le bilan de la semaine.

Règles strictes :
1. Rédige uniquement en français.
2. Le bilan fait entre 200 et 350 mots.
3. Regroupe par grands sujets de la semaine, pas jour par jour. Un sujet qui a évolué d'un jour à l'autre se raconte en une seule fois, avec son aboutissement.
4. Garde les faits, chiffres et décisions importants. N'invente rien qui ne figure pas dans les résumés.
5. Pas de mise en forme (pas de titres, pas de bullets, pas de markdown). Sépare les grands sujets par un saut de ligne (double retour à la ligne), sans titre ni label.
6. Reste factuel, pas d'opinion personnelle."""


def recuperer_resumes_semaine() -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT titre, resume, date_resume,
                   (date_resume AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Paris') AS date_paris
            FROM resumes
            WHERE date_resume >= NOW() - INTERVAL '7 days'
              AND cluster_id <> %s
            ORDER BY date_resume ASC
        """, (CLUSTER_HEBDO,))
        colonnes = [desc[0] for desc in cursor.description]
        return [dict(zip(colonnes, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()


def enregistrer_cluster_hebdo(titre: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO clusters (topic_id, titre, date_run) VALUES (%s, %s, NOW()) RETURNING id",
            (CLUSTER_HEBDO, titre),
        )
        cluster_id = cursor.fetchone()[0]
        conn.commit()
        return cluster_id
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def lancer() -> None:
    debut = time.monotonic()
    log.info("===== BILAN DE LA SEMAINE =====")

    resumes = recuperer_resumes_semaine()
    jours = {r["date_paris"].date() for r in resumes}
    if len(jours) < MIN_JOURS:
        log.info(f"Bilan de la semaine ignoré : {len(jours)} jour(s) de résumés (minimum {MIN_JOURS})")
        return

    blocs = []
    for r in resumes:
        jour = JOURS[r["date_paris"].weekday()]
        blocs.append(f"[{jour}] {r['titre']}\n{r['resume']}")
    contenu, cout = appeler_chat({
        "model": MODEL,
        "reasoning_effort": EFFORTS,
        "verbosity": "low",
        "messages": [
            {"role": "system", "content": INSTRUCTION},
            {"role": "user", "content": "Résumés de la semaine :\n\n" + "\n\n---\n\n".join(blocs)},
        ],
    })

    titre = "Le bilan de la semaine"
    enregistrement_resumes([{
        "cluster_id": CLUSTER_HEBDO,
        "titre": titre,
        "resume": contenu.strip(),
        "cluster_id_fk": enregistrer_cluster_hebdo(titre),
        "prix": cout,
        "nb_articles_rss": None,
    }])

    duree = int(time.monotonic() - debut)
    log.info(f"===== FIN : bilan de {len(resumes)} résumés sur {len(jours)} jours, {cout:.4f} $, {duree} s =====")
    envoyer_notification(
        "NewsIA : bilan de la semaine prêt",
        f"Synthèse de {len(resumes)} résumés sur {len(jours)} jours.\nCoût : {f'{cout:.4f}'.replace('.', ',')} $",
        ["newspaper"],
    )


if __name__ == "__main__":
    try:
        lancer()
    except requests.RequestException as e:
        log.error(f"[!] Bilan de la semaine impossible : {e}")
        raise SystemExit(1)
