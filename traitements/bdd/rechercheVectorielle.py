from traitements.bdd.connexion import get_connection

TOP_K = 10

def recuperer_articles_zonebourse_du_jour() -> list[dict]:
    """
    Récupère tous les articles ZoneBourse des dernières 24h,
    pour constituer le cluster forcé (indépendant du clustering HDBSCAN/GPT).
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, titre, contenu, source, date_ajout
            FROM articles
            WHERE source LIKE 'ZoneBourse%%'
            AND date_ajout >= NOW() - INTERVAL '24 hours'
            AND contenu IS NOT NULL
            ORDER BY date_ajout ASC
        """)
        colonnes = [desc[0] for desc in cursor.description]
        return [dict(zip(colonnes, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()

def rechercher_articles_similaires(embedding: list[float], top_k: int = TOP_K) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, titre, contenu, source, date_ajout,
                   1 - (embedding <=> %s::vector) AS score
            FROM articles
            WHERE embedding IS NOT NULL
              AND date_ajout >= NOW() - INTERVAL '24 hours'
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, (embedding, embedding, top_k))
        colonnes = [desc[0] for desc in cursor.description]
        return [dict(zip(colonnes, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()