from traitements.rss.rss import recuperer_articles_du_jour
from traitements.bdd.connexion import get_connection
from traitements.bdd.communs import embedder_textes

if __name__ == "__main__":
    articles_rss = recuperer_articles_du_jour()

    # Séparation : articles RSS classiques (sans contenu) vs déjà scrapés (ex: ZoneBourse)
    articles_sans_contenu = [a for a in articles_rss if not a.get("contenu")]
    articles_avec_contenu = [a for a in articles_rss if a.get("contenu")]

    conn = get_connection()
    cursor = conn.cursor()
    try:
        # ── Articles RSS classiques — contenu téléchargé plus tard par main.py ──
        for a in articles_sans_contenu:
            cursor.execute("""
                INSERT INTO articles (titre, url, source)
                VALUES (%s, %s, %s)
                ON CONFLICT (url) DO NOTHING
            """, (a["titre"], a["lien"], a["source"]))

        # ── Articles déjà entièrement scrapés (ZoneBourse) — contenu + embedding directs ──
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
        print(f"[+] {len(articles_sans_contenu)} articles RSS insérés (sans contenu)")
        print(f"[+] {len(articles_avec_contenu)} articles pré-scrapés insérés (contenu + embedding)")
    finally:
        cursor.close()
        conn.close()