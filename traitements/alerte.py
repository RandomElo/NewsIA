"""
Alerte Discord quand le traitement quotidien échoue.
Usage (crontab) : python -m traitements.alerte "message"
Le webhook (DISCORD_WEBHOOK) est le même que celui du redémarrage hebdo du Pi
(commun/scripts/.env.discord, injecté par docker-compose). Sans lui, rien n'est envoyé.
"""
import os
import sys

import requests


def main() -> None:
    webhook = os.getenv("DISCORD_WEBHOOK")
    if not webhook:
        print("Pas de DISCORD_WEBHOOK, alerte non envoyée.")
        return
    message = sys.argv[1] if len(sys.argv) > 1 else "Échec du traitement NewsIA"
    try:
        requests.post(
            webhook,
            json={
                "username": "Raspberry Pi",
                "content": "@everyone",
                "allowed_mentions": {"parse": ["everyone"]},
                "embeds": [{"title": "NewsIA : problème", "description": message, "color": 15158332}],
            },
            timeout=15,
        ).raise_for_status()
    except requests.RequestException as e:
        print(f"Alerte Discord non envoyée : {e}")


if __name__ == "__main__":
    main()
