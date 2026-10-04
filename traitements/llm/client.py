import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv
load_dotenv()

LITELLM_URL = os.getenv("LITELLM_PROXY_URL")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY")

# (connexion, lecture) en secondes : une réponse avec raisonnement peut être longue
TIMEOUT = (10, 180)


def _creer_session() -> requests.Session:
    """
    Session partagée pour tous les appels au proxy LiteLLM.
    Retente automatiquement les coupures réseau (dont "Connection reset by peer"),
    les timeouts et les erreurs 429/5xx, avec une attente croissante (0s, 4s, 8s, 16s, 32s).
    """
    retry = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],  # urllib3 ne retente pas les POST par défaut
        raise_on_status=False,     # l'erreur HTTP finale est levée par raise_for_status()
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers["Authorization"] = f"Bearer {LITELLM_API_KEY}"
    return session


_session = _creer_session()


def _poster(endpoint: str, payload: dict) -> requests.Response:
    response = _session.post(f"{LITELLM_URL}/{endpoint}", json=payload, timeout=TIMEOUT)
    response.raise_for_status()
    return response


def appeler_litellm(endpoint: str, payload: dict) -> dict:
    """POST sur le proxy LiteLLM (ex: 'chat/completions', 'embeddings') et retourne le JSON."""
    return _poster(endpoint, payload).json()


def appeler_chat(payload: dict) -> tuple[str, float]:
    """
    Appel chat/completions. Retourne (contenu, coût en dollars).
    Le coût vient de l'en-tête que LiteLLM calcule pour chaque requête. Seuls les
    appels GPT sont comptés : les embeddings Voyage restent dans le quota gratuit.
    """
    response = _poster("chat/completions", payload)
    contenu = response.json()["choices"][0]["message"]["content"]
    cout = float(response.headers.get("x-litellm-response-cost") or 0)
    return contenu, cout
