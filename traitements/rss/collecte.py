from traitements.rss.rss import recuperer_articles_du_jour
from traitements.bdd.connexion import get_connection
from traitements.bdd.communs import embedder_textes
from traitements.journal import log

if __name__ == "__main__":

    articles_rss = recuperer_articles_du_jour()
    articles_sans_contenu = [a for a in articles_rss if not a.get("contenu")]
    articles_avec_contenu = [a for a in articles_rss if a.get("contenu")]

    article_zb = next((a for a in articles_avec_contenu if a["source"].startswith("ZoneBourse")), None)
    etat_zb = f"'{article_zb['titre'][:70]}'" if article_zb else "aucun article du jour"
    log.info(f"Collecte : {len(articles_sans_contenu)} articles RSS, ZoneBourse {etat_zb}")

    conn = get_connection()
    cursor = conn.cursor()
    try:
        for a in articles_sans_contenu:
            cursor.execute("""
                INSERT INTO articles (titre, url, source)
                VALUES (%s, %s, %s)
                ON CONFLICT (url) DO NOTHING
            """, (a["titre"], a["lien"], a["source"]))

        if articles_avec_contenu:
            textes = [f"{a['titre']} {a['contenu']}" for a in articles_avec_contenu]
            embeddings = embedder_textes(textes)
            for a, embedding in zip(articles_avec_contenu, embeddings):
                cursor.execute("""
                    INSERT INTO articles (titre, url, source, contenu, embedding)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (url) DO UPDATE
                    SET contenu = EXCLUDED.contenu, embedding = EXCLUDED.embedding
                """, (a["titre"], a["lien"], a["source"], a["contenu"], embedding))

        conn.commit()
    finally:
        cursor.close()
        conn.close()