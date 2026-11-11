from traitements.bdd.connexion import get_connection
from traitements.clustering.hdbscan import clusturiser_titres
from traitements.llm.analyseCluster import analyser_clusters
from traitements.rss.rss import telecharger_et_enregistrer
from traitements.rag.generationRequete import rag_pour_tous_les_clusters
from traitements.llm.resumeFinal import resumer_tous_les_clusters, resumer_cluster
from traitements.bdd.enregistrementResumes import enregistrement_resumes
from traitements.bdd.rechercheVectorielle import recuperer_articles_zonebourse_du_jour
from traitements.bdd.resumesPrecedents import recuperer_resumes_recents
from traitements.journal import log
from traitements.periode import fin
from traitements.notification import envoyer_notification

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
            AND date_ajout >= COALESCE(%s::timestamp, NOW()) - INTERVAL '24 hours'
            AND date_ajout < COALESCE(%s::timestamp, NOW())
        """, (fin(), fin()))
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
        # Limité à la fenêtre traitée : un rattrapage ne doit pas supprimer la collecte suivante
        cursor.execute("""
            DELETE FROM articles
            WHERE embedding IS NULL
            AND url NOT LIKE 'podcast://%%'
            AND date_ajout < COALESCE(%s::timestamp, NOW())
        """, (fin(),))
        log.info(f"{cursor.rowcount} articles non retenus supprimés")
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def construire_cluster_force_zonebourse(articles: list[dict], resumes_precedents: list[dict]) -> dict | None:
    """
    Construit un cluster 'forcé' contenant tous les articles ZoneBourse du jour,
    sans passer par la recherche vectorielle (on les veut tous, pas une sélection).
    Le dernier tour d'horizon publié est joint pour que le résumé ne répète pas la veille.
    """
    if not articles:
        return None
    precedent = next((r for r in resumes_precedents if r["cluster_id"] == "zonebourse-force"), None)
    return {
        "cluster_id": "zonebourse-force",
        "titre": "Tour d'horizon ZoneBourse",
        "questions": [],
        "articles": articles,
        "resume_precedent": precedent["resume"] if precedent else None,
    }


def joindre_resumes_precedents(rag_resultats: list[dict], resumes_precedents: list[dict]) -> None:
    """Ajoute à chaque sujet que GPT a marqué comme suite (suite_de = 'R<id>') le texte du résumé poursuivi."""
    par_id = {f"R{r['id']}": r["resume"] for r in resumes_precedents}
    for cluster in rag_resultats:
        cluster["resume_precedent"] = par_id.get(cluster.get("suite_de", ""))


def lancer(titre_notification: str = "NewsIA : résumés du jour prêts") -> None:
    debut = time.monotonic()
    log.info("===== TRAITEMENT =====")

    articles_rss = recuperer_articles_bdd()
    log.info(f"{len(articles_rss)} articles collectés sur 24 h")

    # Sujets des jours précédents : GPT écarte ceux qui n'ont pas de fait nouveau
    resumes_precedents = recuperer_resumes_recents()

    clusters = clusturiser_titres(articles_rss)
    try:
        analyse = analyser_clusters(clusters, resumes_precedents)
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
    joindre_resumes_precedents(rag_resultats, resumes_precedents)
    resumes =resumer_tous_les_clusters(rag_resultats, analyse["cout"], len(articles_rss))

    articles_zb = recuperer_articles_zonebourse_du_jour()
    cluster_zb = construire_cluster_force_zonebourse(articles_zb, resumes_precedents)
    if cluster_zb:
        try:
            resume_zb = resumer_cluster(cluster_zb)
        except requests.RequestException as e:
            log.error(f"[!] Résumé ZoneBourse impossible : {e}")
            resume_zb = None
        if resume_zb:
            resume_zb["nb_articles_rss"] = len(articles_rss)
            enregistrement_resumes([resume_zb])
            resumes.append(resume_zb)

    nettoyer_articles_non_traites()

    cout_total = sum(r["prix"] for r in resumes)
    duree = int(time.monotonic() - debut)
    log.info(f"===== FIN : {len(resumes)} résumés, {cout_total:.4f} $, {duree // 60} min {duree % 60:02d} s =====")

    cout_fr = f"{cout_total:.4f}".replace(".", ",")
    envoyer_notification(
        titre_notification,
        f"{len(resumes)} résumés générés à partir de {len(articles_rss)} articles RSS.\n"
        f"Coût : {cout_fr} $\n"
        f"Durée : {duree // 60} min {duree % 60:02d} s",
        ["newspaper"],
    )


if __name__ == "__main__":
    lancer()
