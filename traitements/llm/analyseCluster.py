import json
from traitements.config.prompts import ANALYSE_CLUSTERS_INSTRUCTION, ANALYSE_CLUSTERS_SCHEMA
from traitements.llm.client import appeler_chat
from traitements.journal import log

MODEL = "openai/gpt-5.4-nano"
EFFORTS = "low"

def formater_clusters_yaml(clusters: dict[int, list[dict]]) -> str:
    lignes = []
    for cluster_id, articles in clusters.items():
        lignes.append(f"'{cluster_id}':")
        for article in articles:
            titre_echappe = article["titre"].replace("'", "''")
            lignes.append(f"  - '{titre_echappe}'")
    return "\n".join(lignes)
def analyser_clusters(clusters: dict[int, list[dict]]) -> dict:
    """
    Envoie les clusters à GPT et retourne l'analyse structurée.
    Retourne un dict avec 'clusters', 'importance_order' et 'cout' (dollars).
    """
    yaml_clusters = formater_clusters_yaml(clusters)

    contenu, cout = appeler_chat({
        "model": MODEL,
        "reasoning_effort": EFFORTS,
        "response_format": ANALYSE_CLUSTERS_SCHEMA,
        "messages": [
            {"role": "system", "content": ANALYSE_CLUSTERS_INSTRUCTION},
            {"role": "user", "content": yaml_clusters}
        ]
    })

    resultat = json.loads(contenu)
    resultat["cout"] = cout

    log.info(f"GPT : {len(resultat['clusters'])} sujets retenus ({cout:.4f} $)")

    return resultat