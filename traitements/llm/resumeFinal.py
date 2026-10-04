import requests
from traitements.bdd.enregistrementResumes import enregistrement_resumes
from traitements.bdd.enregistrementCluster import enregistrer_cluster
from traitements.llm.client import appeler_chat
from traitements.journal import log

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
    et retourne { cluster_id, titre, resume, cluster_id_fk, prix }.
    prix : coût en dollars de l'appel GPT qui a rédigé le résumé.
    """
    cluster_id = cluster_rag["cluster_id"]
    titre = cluster_rag["titre"]
    articles = cluster_rag["articles"]

    if not articles:
        log.warning(f"[!] Résumé '{titre}' : aucun article, ignoré")
        return None

    # Filtre unique : les articles peu pertinents sont écartés à la fois
    # du contexte envoyé au LLM et de la liaison enregistrée en BDD.
    articles_pertinents = [a for a in articles if a.get("score", 1) >= SCORE_MIN]
    if not articles_pertinents:
        articles_pertinents = [max(articles, key=lambda a: a.get("score", 0))]

    contexte = formater_contexte(articles_pertinents)
    prompt_user = f"""Sujet : {titre}

Articles :
{contexte}"""

    resume, cout = appeler_chat({
        "model": MODEL,
        "reasoning_effort": EFFORTS,
        "verbosity": "low",
        "messages": [
            {"role": "system", "content": INSTRUCTION},
            {"role": "user", "content": prompt_user}
        ]
    })

    resume = resume.strip()
    log.info(f"Résumé '{titre[:70]}' : {len(articles_pertinents)}/{len(articles)} articles, {cout:.4f} $")

    # Enregistré seulement une fois le résumé obtenu, pour ne pas laisser de cluster orphelin en BDD
    cluster_id_fk = enregistrer_cluster(cluster_id, titre, articles_pertinents)

    return {
        "cluster_id": cluster_id,
        "titre": titre,
        "resume": resume,
        "cluster_id_fk": cluster_id_fk,
        "prix": cout,
    }


def resumer_tous_les_clusters(rag_resultats: list[dict], cout_analyse: float = 0) -> list[dict]:
    """
    Prend tous les résultats RAG et génère un résumé pour chaque cluster.
    Retourne la liste dans l'ordre d'importance (celui du RAG).
    cout_analyse : coût de l'appel GPT de choix des clusters, réparti à parts égales
    sur les résumés pour que la somme des prix corresponde au coût réel de la journée.
    """
    resultats = []
    for cluster_rag in rag_resultats:
        # Un cluster en échec (même après les retries) ne doit pas faire perdre les autres
        try:
            resume = resumer_cluster(cluster_rag)
        except requests.RequestException as e:
            log.error(f"[!] Résumé '{cluster_rag['titre']}' impossible : {e}")
            continue
        if resume:
            resultats.append(resume)

    for resume in resultats:
        resume["prix"] += cout_analyse / len(resultats)

    enregistrement_resumes(resultats)
    return resultats