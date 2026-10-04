from traitements.bdd.communs import generer_embedding
from traitements.bdd.rechercheVectorielle import rechercher_articles_similaires
from traitements.journal import log

def rag_pour_cluster(topic: dict) -> dict:
    titre     = topic["title"]
    questions = topic["questions"]
    topic_id  = topic["id"]

    ids_vus          = set()
    articles_uniques = []

    # ── Recherche vectorielle normale ──────────────────────────────────────────
    for question in questions:
        embedding = generer_embedding(question)
        resultats = rechercher_articles_similaires(embedding)
        for article in resultats:
            if article["id"] not in ids_vus:
                ids_vus.add(article["id"])
                articles_uniques.append(article)

    articles_uniques.sort(key=lambda a: a["score"], reverse=True)

    return {
        "cluster_id": topic_id,
        "titre":      titre,
        "questions":  questions,
        "articles":   articles_uniques,
    }


def rag_pour_tous_les_clusters(analyse: dict) -> list[dict]:
    topics           = {t["id"]: t for t in analyse["clusters"]}
    importance_order = analyse["importance_order"]

    resultats = []
    for topic_id in importance_order:
        topic = topics.get(topic_id)
        if not topic:
            continue

        resultats.append(rag_pour_cluster(topic))

    log.info(f"RAG : {len(resultats)} sujets, {sum(len(r['articles']) for r in resultats)} articles trouvés")
    return resultats