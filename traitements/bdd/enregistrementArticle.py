from traitements.bdd.connexion import get_connection
from traitements.bdd.communs import embedder_textes
from traitements.journal import log


def ajouter_articles_batch(articles: list[dict]) -> list[int]:
    if not articles:
        return []

    textes = [f"{a.get('titre', '')} {a.get('contenu', '')}" for a in articles]
    embeddings = embedder_textes(textes)

    conn = get_connection()
    cursor = conn.cursor()
    ids = []
    try:
        for article, embedding in zip(articles, embeddings):
            cursor.execute("""
                UPDATE articles
                SET contenu = %s, embedding = %s
                WHERE url = %s
                RETURNING id
            """, (
                article.get("contenu"),
                embedding,
                article.get("url"),
            ))
            row = cursor.fetchone()
            if row:
                ids.append(row[0])

        conn.commit()
        return ids
    except Exception as e:
        log.error(f"[!] Erreur update batch : {e}")
        conn.rollback()
        return []
    finally:
        cursor.close()
        conn.close()