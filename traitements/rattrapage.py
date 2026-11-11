"""
Rejoue le traitement d'un jour passé, quand celui de 23h50 a échoué.

Prend les articles collectés entre la veille 23h50 et ce jour-là 23h50 (heure de Paris),
comme l'aurait fait le cron, et enregistre les résumés à la date de ce jour.
Les articles collectés après cette fenêtre ne sont pas touchés : ils restent pour le prochain traitement.

    python -m traitements.rattrapage 2026-10-17
    python -m traitements.rattrapage            # hier par défaut
"""
import sys
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from traitements.journal import log
from traitements.main import lancer
from traitements.periode import definir_fin

HEURE_TRAITEMENT = time(23, 50)
PARIS = ZoneInfo("Europe/Paris")


def fin_de_fenetre(jour: date) -> datetime:
    """23h50 heure de Paris ce jour-là, en UTC sans fuseau comme les colonnes de la BDD."""
    locale = datetime.combine(jour, HEURE_TRAITEMENT, tzinfo=PARIS)
    return locale.astimezone(timezone.utc).replace(tzinfo=None)


if __name__ == "__main__":
    aujourd_hui = datetime.now(PARIS).date()
    jour = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else aujourd_hui - timedelta(days=1)
    if jour >= aujourd_hui:
        sys.exit(f"Le rattrapage ne concerne que les jours passés (reçu {jour}).")

    definir_fin(fin_de_fenetre(jour))
    log.info(f"Rattrapage du {jour:%d/%m/%Y}")
    lancer(f"NewsIA : résumés du {jour:%d/%m} prêts (rattrapage)")
