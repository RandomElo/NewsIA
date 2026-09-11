import os
import json
import requests
from dotenv import load_dotenv
from traitements.config.prompts import ANALYSE_CLUSTERS_INSTRUCTION, ANALYSE_CLUSTERS_SCHEMA
load_dotenv()

LITELLM_URL = os.getenv("LITELLM_PROXY_URL")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY")

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
    Retourne un dict avec 'clusters' et 'importance_order'.
    """
    yaml_clusters = formater_clusters_yaml(clusters)

    print("[*] Envoi à GPT pour analyse...")
    response = requests.post(
        f"{LITELLM_URL}/chat/completions",
        headers={"Authorization": f"Bearer {LITELLM_API_KEY}"},
        json={
            "model": MODEL,
            "reasoning_effort": EFFORTS,
            "response_format": ANALYSE_CLUSTERS_SCHEMA,
            "messages": [
                {"role": "system", "content": ANALYSE_CLUSTERS_INSTRUCTION},
                {"role": "user", "content": yaml_clusters}
            ]
        }
    )
    response.raise_for_status()

    contenu = response.json()["choices"][0]["message"]["content"]
    resultat = json.loads(contenu)

    print(f"[+] {len(resultat['clusters'])} clusters sélectionnés par GPT")
    print(f"[+] Ordre d'importance : {resultat['importance_order']}")

    return resultat