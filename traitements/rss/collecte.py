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

    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Les flux renvoient en partie les mêmes articles d'une collecte à l'autre :
        # seuls ceux réellement insérés comptent comme nouveaux
        nb_nouveaux = 0
        for a in articles_sans_contenu:
            cursor.execute("""
                INSERT INTO articles (titre, url, source)
                VALUES (%s, %s, %s)
                ON CONFLICT (url) DO NOTHING
            """, (a["titre"], a["lien"], a["source"]))
            nb_nouveaux += cursor.rowcount

        if articles_avec_contenu:
            textes = [f"{a['titre']} {a['contenu']}" for a in articles_avec_contenu]
            embeddings = embedder_textes(textes)
            for a, embedding in zip(articles_avec_contenu, embeddings):
                cursor.execute("""
                    INSERT INTO articles (titre, url, source, contenu, embedding)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (url) DO UPDATE
                    SET contenu = EXCLUDED.contenu, embedding = EXCLUDED.embedding
                    RETURNING (xmax = 0)
                """, (a["titre"], a["lien"], a["source"], a["contenu"], embedding))
                # xmax = 0 : la ligne vient d'être insérée (et non mise à jour)
                nb_nouveaux += cursor.fetchone()[0]

        # Historique conservé : la table articles est nettoyée chaque soir par main.py
        cursor.execute("""
            INSERT INTO collectes (nb_articles_flux, nb_nouveaux)
            VALUES (%s, %s)
        """, (len(articles_rss), nb_nouveaux))

        conn.commit()
        log.info(f"Collecte : {len(articles_sans_contenu)} articles RSS dont {nb_nouveaux} nouveaux, ZoneBourse {etat_zb}")
    finally:
        cursor.close()
        conn.close()