import os
import requests
from dotenv import load_dotenv
from traitements.journal import log
load_dotenv()

NTFY_TOPIC = os.getenv("NTFY_TOPIC")


def envoyer_notification(titre: str, message: str, tags: list[str] | None = None) -> None:
    """
    Envoie une notification ntfy.sh sur le topic NTFY_TOPIC (rien si la variable est absente).
    Envoi en JSON plutôt qu'en en-têtes HTTP, qui n'acceptent pas les accents du titre.
    Ne lève jamais d'exception : une notification ratée ne doit pas faire échouer le traitement.
    """
    if not NTFY_TOPIC:
        return
    try:
        requests.post(
            "https://ntfy.sh/",
            json={"topic": NTFY_TOPIC, "title": titre, "message": message, "tags": tags or []},
            timeout=15,
        ).raise_for_status()
    except requests.RequestException as e:
        log.warning(f"Notification ntfy non envoyée : {e}")
