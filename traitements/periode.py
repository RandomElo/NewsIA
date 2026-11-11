from datetime import datetime

# Fin de la fenêtre de 24 h traitée, en UTC sans fuseau (comme les colonnes de la BDD).
# None pour le traitement normal : les requêtes utilisent alors NOW().
# Un rattrapage (traitements.rattrapage) la fixe pour rejouer un jour passé.
_fin: datetime | None = None


def definir_fin(instant_utc: datetime) -> None:
    global _fin
    _fin = instant_utc


def fin() -> datetime | None:
    """À passer en paramètre SQL sous la forme COALESCE(%s::timestamp, NOW())."""
    return _fin
