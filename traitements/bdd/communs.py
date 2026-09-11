import os
import requests
from dotenv import load_dotenv

load_dotenv()

LITELLM_URL = os.getenv("LITELLM_PROXY_URL")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY")
EMBEDDING_MODEL = "voyage/voyage-4"
MAX_TOKENS = 32000


def count_tokens(text: str) -> int:
    """Approximation : ~4 caractères par token."""
    return len(text) // 4


def bulk_embed(texts: list[str]) -> list[list[float]]:
    """Embed une liste de textes en une seule requête."""
    assert len(texts) <= 1000, "Maximum 1000 textes par batch"
    response = requests.post(
        f"{LITELLM_URL}/embeddings",
        headers={"Authorization": f"Bearer {LITELLM_API_KEY}"},
        json={"model": EMBEDDING_MODEL, "input": texts}
    )
    response.raise_for_status()
    return [item["embedding"] for item in response.json()["data"]]


def dispatch_batches(texts: list[str]) -> list[list[int]]:
    """
    Découpe les indices des textes en batches respectant les limites de tokens.
    Retourne des listes d'indices pour conserver la correspondance avec les données originales.
    """
    indices_tries = sorted(range(len(texts)), key=lambda i: count_tokens(texts[i]), reverse=True)

    batches = []
    batch = []
    total_tokens = 0

    for idx in indices_tries:
        tokens = count_tokens(texts[idx])
        if len(batch) >= 1000 or total_tokens + tokens > MAX_TOKENS:
            batches.append(batch)
            batch = []
            total_tokens = 0
        batch.append(idx)
        total_tokens += tokens

    if batch:
        batches.append(batch)

    return batches


def embedder_textes(texts: list[str]) -> list[list[float]]:
    """
    Embed une liste de textes en gérant automatiquement le batching.
    Retourne les embeddings dans le même ordre que les textes en entrée.
    """
    embeddings = [None] * len(texts)

    for batch_indices in dispatch_batches(texts):
        batch_texts = [texts[i] for i in batch_indices]
        batch_embeddings = bulk_embed(batch_texts)
        for idx, embedding in zip(batch_indices, batch_embeddings):
            embeddings[idx] = embedding

    return embeddings


def generer_embedding(texte: str) -> list[float]:
    """Embed un seul texte."""
    return bulk_embed([texte])[0]