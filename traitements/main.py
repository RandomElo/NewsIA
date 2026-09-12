from traitements.bdd.connexion import get_connection
from traitements.clustering.hdbscan import clusturiser_titres
from traitements.llm.analyseCluster import analyser_clusters
from traitements.rss.rss import telecharger_et_enregistrer
from traitements.rag.generationRequete import rag_pour_tous_les_clusters
from traitements.llm.resumeFinal import resumer_tous_les_clusters, resumer_cluster
from traitements.bdd.enregistrementResumes import enregistrement_resumes
from traitements.bdd.rechercheVectorielle import recuperer_articles_zonebourse_du_jour

from datetime import datetime

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def recuperer_articles_bdd() -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT titre, url, source FROM articles
            WHERE embedding IS NULL
            AND date_ajout >= NOW() - INTERVAL '24 hours'
        """)
        return [
            {"titre": row[0], "lien": row[1], "source": row[2], "description": ""}
            for row in cursor.fetchall()
        ]
    finally:
        cursor.close()
        conn.close()


def nettoyer_articles_non_traites():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            DELETE FROM articles
            WHERE embedding IS NULL
            AND url NOT LIKE 'podcast://%'
        """)
        print(f"[+] {cursor.rowcount} articles non traités supprimés")
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def construire_cluster_force_zonebourse(articles: list[dict]) -> dict | None:
    """
    Construit un cluster 'forcé' contenant tous les articles ZoneBourse du jour,
    sans passer par la recherche vectorielle (on les veut tous, pas une sélection).
    """
    if not articles:
        return None
    return {
        "cluster_id": "zonebourse-force",
        "titre": "Tour d'horizon ZoneBourse",
        "questions": [],
        "articles": articles,
    }


if __name__ == "__main__":
    log("===== TRAITEMENT =====")

    articles_rss = recuperer_articles_bdd()
    log(f"{len(articles_rss)} articles récupérés")

    clusters = clusturiser_titres(articles_rss)
    log("Appel ChatGPT (choix des clusters)")
    analyse = analyser_clusters(clusters)

    urls_selectionnees = set()
    for topic in analyse["clusters"]:
        for cid in topic["cluster_ids"]:
            for article in clusters.get(int(cid), []):
                urls_selectionnees.add(article["lien"])

    telecharger_et_enregistrer(articles_rss, urls_selectionnees)

    rag_resultats = rag_pour_tous_les_clusters(analyse)
    log(f"Rédaction de {len(rag_resultats)} articles")
    resumes = resumer_tous_les_clusters(rag_resultats)
    log("Enregistrement en BDD")

    articles_zb = recuperer_articles_zonebourse_du_jour()
    cluster_zb = construire_cluster_force_zonebourse(articles_zb)
    if cluster_zb:
        resume_zb = resumer_cluster(cluster_zb)
        if resume_zb:
            enregistrement_resumes([resume_zb])

    nettoyer_articles_non_traites()