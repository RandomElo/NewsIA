from traitements.bdd.connexion import get_connection
from traitements.clustering.hdbscan import clusturiser_titres
from traitements.llm.analyseCluster import analyser_clusters
from traitements.rss.rss import telecharger_et_enregistrer
from traitements.rag.generationRequete import rag_pour_tous_les_clusters
from traitements.llm.resumeFinal import resumer_tous_les_clusters, resumer_cluster
from traitements.bdd.enregistrementResumes import enregistrement_resumes
from traitements.bdd.rechercheVectorielle import recuperer_articles_zonebourse_du_jour
from traitements.journal import log

import sys
import time

import requests

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
        log.info(f"{cursor.rowcount} articles non retenus supprimés")
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
    debut = time.monotonic()
    log.info("===== TRAITEMENT =====")

    articles_rss = recuperer_articles_bdd()
    log.info(f"{len(articles_rss)} articles collectés sur 24 h")

    clusters = clusturiser_titres(articles_rss)
    try:
        analyse = analyser_clusters(clusters)
    except requests.RequestException as e:
        # On s'arrête avant nettoyer_articles_non_traites() pour ne pas supprimer la collecte
        log.error(f"[!] Analyse GPT impossible après plusieurs tentatives : {e}")
        sys.exit(1)

    urls_selectionnees = set()
    for topic in analyse["clusters"]:
        for cid in topic["cluster_ids"]:
            for article in clusters.get(int(cid), []):
                urls_selectionnees.add(article["lien"])

    telecharger_et_enregistrer(articles_rss, urls_selectionnees)

    rag_resultats = rag_pour_tous_les_clusters(analyse)
    resumes = resumer_tous_les_clusters(rag_resultats, analyse["cout"])

    articles_zb = recuperer_articles_zonebourse_du_jour()
    cluster_zb = construire_cluster_force_zonebourse(articles_zb)
    if cluster_zb:
        try:
            resume_zb = resumer_cluster(cluster_zb)
        except requests.RequestException as e:
            log.error(f"[!] Résumé ZoneBourse impossible : {e}")
            resume_zb = None
        if resume_zb:
            enregistrement_resumes([resume_zb])
            resumes.append(resume_zb)

    nettoyer_articles_non_traites()

    cout_total = sum(r["prix"] for r in resumes)
    duree = int(time.monotonic() - debut)
    log.info(f"===== FIN : {len(resumes)} résumés, {cout_total:.4f} $, {duree // 60} min {duree % 60:02d} s =====")