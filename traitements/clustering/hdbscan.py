import numpy as np
from sklearn.cluster import HDBSCAN
from traitements.bdd.communs import embedder_textes
from traitements.bdd.connexion import get_connection


def _sauvegarder_embeddings_titres(articles: list[dict], embeddings: list[list[float]]) -> None:
    """
    Met à jour embedding_titre pour chaque article déjà en BDD.
    Opère en batch via executemany.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        donnees = [
            (embedding, article["lien"])
            for article, embedding in zip(articles, embeddings)
        ]
        cursor.executemany(
            "UPDATE articles SET embedding_titre = %s WHERE url = %s",
            donnees,
        )
        conn.commit()
        print(f"[+] {cursor.rowcount} embedding_titre sauvegardés")
    except Exception as e:
        print(f"[!] Erreur sauvegarde embedding_titre : {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def clusturiser_titres(articles: list[dict]) -> dict[int, list[dict]]:
    """
    Clusturise une liste d'articles RSS sur leurs titres uniquement.
    Sauvegarde les embeddings de titres en BDD au passage.
    Ignore le bruit (label -1).

    articles : list[dict] — { titre, lien, source, description, ... }
    Retourne { cluster_id: [article, ...] } sans le cluster -1
    """
    if not articles:
        return {}

    print(f"[*] Clustering de {len(articles)} titres...")

    titres = [a["titre"] for a in articles]
    embeddings = embedder_textes(titres)

    _sauvegarder_embeddings_titres(articles, embeddings)

    clusterer = HDBSCAN(
        min_cluster_size=4,
        min_samples=2,
        metric="euclidean",
        cluster_selection_method="leaf"
    )
    labels = clusterer.fit_predict(np.array(embeddings))

    nb_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    nb_bruit = list(labels).count(-1)
    print(f"[+] {nb_clusters} clusters trouvés, {nb_bruit} articles ignorés (bruit)")

    clusters = {}
    for article, label in zip(articles, labels):
        if label == -1:
            continue
        clusters.setdefault(int(label), []).append(article)

    return clusters