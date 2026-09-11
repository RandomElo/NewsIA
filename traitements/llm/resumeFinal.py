import os
import requests
from dotenv import load_dotenv
from traitements.bdd.enregistrementResumes import enregistrement_resumes
from traitements.bdd.enregistrementCluster import enregistrer_cluster
load_dotenv()

LITELLM_URL = os.getenv("LITELLM_PROXY_URL")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY")

MODEL = "openai/gpt-5.4-nano"
EFFORTS = "low"

SCORE_MIN = 0.5  # seuil sous lequel un article est jugé hors-sujet pour ce cluster

INSTRUCTION = """Tu es un journaliste de télévision francophone expert en synthèse d'actualité.
On te donne un sujet (titre) et une liste d'articles de presse sur ce sujet.
Tu dois produire un résumé clair, factuel et structuré en français.

Règles strictes :
1. Rédige uniquement en français, même si les articles sources sont dans d'autres langues.
2. Le résumé doit faire entre 100 et 180 mots.
3. Structure narrative en trois temps : les faits principaux d'abord, puis le contexte, puis les perspectives — mais cet enchaînement doit rester fluide et journalistique. N'utilise JAMAIS les mots "Contexte", "Perspective(s)", "Faits principaux" ou toute autre étiquette similaire comme préfixe, titre ou mot de liaison explicite. Le changement de partie doit se sentir naturellement dans le texte (ex: "Sur le fond, ...", "Cette affaire s'inscrit dans ...", "À l'avenir, ..."), jamais être annoncé par un label.
4. N'invente et ne force jamais de contexte ou de perspective si les articles sources n'en fournissent pas suffisamment : dans ce cas, reste concentré sur les faits plutôt que de remplir artificiellement chaque partie.
5. Pas de mise en forme (pas de titres, pas de bullets, pas de markdown).
6. Reste factuel, pas d'opinion personnelle.
7. Si les articles se contredisent, mentionne les deux versions.
8. Si les articles couvrent en réalité deux sujets distincts et clairement séparés (par exemple deux actualités technologiques différentes réunies sous le même thème), ne les mélange jamais dans un même paragraphe : traite chaque sujet dans son propre paragraphe, séparé par un saut de ligne (double retour à la ligne). N'ajoute pas de titre ou de label avant chaque paragraphe, seulement le saut de ligne."""


def formater_contexte(articles: list[dict]) -> str:
    """Concatène tous les articles RAG en un seul bloc texte."""
    blocs = []
    for article in articles:
        titre = article.get("titre", "").strip()
        contenu = article.get("contenu", "").strip()
        if titre or contenu:
            blocs.append(f"TITRE: {titre}\n{contenu}")
    return "\n\n---\n\n".join(blocs)


def resumer_cluster(cluster_rag: dict) -> dict | None:
    """
    Prend un cluster RAG { cluster_id, titre, questions, articles }
    et retourne { cluster_id, titre, resume, cluster_id_fk }.
    """
    cluster_id = cluster_rag["cluster_id"]
    titre = cluster_rag["titre"]
    articles = cluster_rag["articles"]

    if not articles:
        print(f"  [~] Cluster {cluster_id} — pas d'articles, ignoré")
        return None

    # Filtre unique : les articles peu pertinents sont écartés à la fois
    # du contexte envoyé au LLM et de la liaison enregistrée en BDD.
    articles_pertinents = [a for a in articles if a.get("score", 1) >= SCORE_MIN]
    if not articles_pertinents:
        print(f"  [~] Cluster {cluster_id} — aucun article au-dessus du seuil, on garde le meilleur quand même")
        articles_pertinents = [max(articles, key=lambda a: a.get("score", 0))]

    print(f"[*] Résumé cluster {cluster_id} — '{titre}' ({len(articles_pertinents)}/{len(articles)} articles retenus)")

    cluster_id_fk = enregistrer_cluster(cluster_id, titre, articles_pertinents)

    contexte = formater_contexte(articles_pertinents)
    prompt_user = f"""Sujet : {titre}

Articles :
{contexte}"""

    response = requests.post(
        f"{LITELLM_URL}/chat/completions",
        headers={"Authorization": f"Bearer {LITELLM_API_KEY}"},
        json={
            "model": MODEL,
            "reasoning_effort": EFFORTS,
            "verbosity": "low",
            "messages": [
                {"role": "system", "content": INSTRUCTION},
                {"role": "user", "content": prompt_user}
            ]
        }
    )
    response.raise_for_status()

    resume = response.json()["choices"][0]["message"]["content"].strip()
    print(f"  [+] {len(resume)} caractères générés")

    return {
        "cluster_id": cluster_id,
        "titre": titre,
        "resume": resume,
        "cluster_id_fk": cluster_id_fk,
    }


def resumer_tous_les_clusters(rag_resultats: list[dict]) -> list[dict]:
    """
    Prend tous les résultats RAG et génère un résumé pour chaque cluster.
    Retourne la liste dans l'ordre d'importance (celui du RAG).
    """
    resultats = []
    for cluster_rag in rag_resultats:
        resume = resumer_cluster(cluster_rag)
        if resume:
            resultats.append(resume)

    print(f"[+] {len(resultats)} résumés générés")
    enregistrement_resumes(resultats)
    return resultats