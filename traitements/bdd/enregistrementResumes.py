from traitements.bdd.connexion import get_connection
from traitements.journal import log


def enregistrement_resumes(resumes: list[dict]) -> None:
    """
    Sauvegarde une liste de résumés en BDD.
    resumes : list[dict] — chaque dict { cluster_id, titre, resume, cluster_id_fk (optionnel), prix (optionnel),
               nb_articles_rss (optionnel) }
    """
    if not resumes:
        return

    conn = get_connection()
    cursor = conn.cursor()
    try:
        for r in resumes:
            cursor.execute(
                """
                INSERT INTO resumes (cluster_id, titre, resume, cluster_id_fk, prix, nb_articles_rss)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (r["cluster_id"], r["titre"], r["resume"], r.get("cluster_id_fk"), r.get("prix"),
                 r.get("nb_articles_rss")),
            )
        conn.commit()
    except Exception as e:
        log.error(f"[!] Erreur sauvegarde résumés : {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()