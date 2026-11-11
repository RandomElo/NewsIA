from traitements.bdd.connexion import get_connection
from traitements.journal import log
from traitements.periode import fin


def enregistrer_cluster(topic_id: str, titre: str, articles: list[dict]) -> int | None:
    """
    Insère un cluster en BDD et crée les liaisons avec ses articles sources.

    topic_id  : identifiant GPT du topic (ex: "1", "2", ...)
    titre     : titre journalistique du cluster
    articles  : articles RAG associés — chaque dict doit avoir un champ "id"

    Retourne l'id du cluster inséré, ou None en cas d'erreur.
    """
    if not articles:
        return None

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO clusters (topic_id, titre, date_run) VALUES (%s, %s, COALESCE(%s::timestamp, NOW())) RETURNING id",
            (topic_id, titre, fin()),
        )
        cluster_id = cursor.fetchone()[0]

        ids_articles = list({a["id"] for a in articles if a.get("id")})
        if ids_articles:
            cursor.executemany(
                "INSERT INTO cluster_articles (cluster_id, article_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                [(cluster_id, article_id) for article_id in ids_articles],
            )

        conn.commit()
        return cluster_id

    except Exception as e:
        log.error(f"[!] Erreur enregistrement cluster {topic_id} : {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()
        conn.close()