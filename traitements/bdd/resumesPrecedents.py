from traitements.bdd.connexion import get_connection
from traitements.periode import fin

JOURS_HISTORIQUE = 3


def recuperer_resumes_recents(jours: int = JOURS_HISTORIQUE) -> list[dict]:
    """
    Résumés publiés ces derniers jours, pour que le choix des sujets et la rédaction
    sachent ce qui a déjà été dit et évitent de répéter les mêmes sujets d'un jour à l'autre.
    Retourne list[dict] { id, cluster_id, titre, resume, date_resume }, du plus récent au plus ancien.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, cluster_id, titre, resume, date_resume
            FROM resumes
            WHERE date_resume >= COALESCE(%s::timestamp, NOW()) - make_interval(days => %s)
              AND date_resume < COALESCE(%s::timestamp, NOW())
              AND cluster_id <> 0  -- le bilan hebdo n'est pas un sujet à poursuivre
            ORDER BY date_resume DESC
        """, (fin(), jours, fin()))
        colonnes = [desc[0] for desc in cursor.description]
        return [dict(zip(colonnes, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()
