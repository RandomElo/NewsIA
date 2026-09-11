from traitements.bdd.communs import generer_embedding
from traitements.bdd.rechercheVectorielle import rechercher_articles_similaires

def rag_pour_cluster(topic: dict) -> dict:
    titre     = topic["title"]
    questions = topic["questions"]
    topic_id  = topic["id"]

    print(f"[*] RAG topic {topic_id} — '{titre}' ({len(questions)} questions)")

    ids_vus          = set()
    articles_uniques = []

    # ── Recherche vectorielle normale ──────────────────────────────────────────
    for i, question in enumerate(questions):
        print(f"  [{i+1}/{len(questions)}] {question[:80]}...")
        embedding = generer_embedding(question)
        resultats = rechercher_articles_similaires(embedding)
        for article in resultats:
            if article["id"] not in ids_vus:
                ids_vus.add(article["id"])
                articles_uniques.append(article)

    articles_uniques.sort(key=lambda a: a["score"], reverse=True)

    print(f"  [+] {len(articles_uniques)} articles uniques trouvés")

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

    print(f"[+] RAG terminé — {len(resultats)} topics traités")
    return resultats