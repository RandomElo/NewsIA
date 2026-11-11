"""
Regénère les embeddings manquants des articles qui ont encore leur texte.

Utile après une perte de données (les embeddings, stockés en TOAST, étaient les
premiers touchés par la corruption du 2026-11-10). Même texte que l'enregistrement
normal (bdd/enregistrementArticle.py) : "titre contenu".

Usage : docker exec news-traitements python -m traitements.regenerer_embeddings
"""
import sys

from traitements.bdd.communs import embedder_textes
from traitements.bdd.connexion import get_connection
from traitements.journal import log

PAQUET = 40  # articles par appel, pour limiter la mémoire et réessayer facilement


def main() -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, titre, contenu FROM articles "
        "WHERE contenu IS NOT NULL AND embedding IS NULL ORDER BY id"
    )
    lignes = cur.fetchall()
    log.info(f"{len(lignes)} articles à régénérer")

    faits = 0
    for debut in range(0, len(lignes), PAQUET):
        lot = lignes[debut:debut + PAQUET]
        textes = [f"{titre or ''} {contenu or ''}" for _, titre, contenu in lot]
        try:
            embeddings = embedder_textes(textes)
        except Exception as e:  # on continue avec le lot suivant
            log.error(f"[!] lot {debut} ignoré : {e}")
            continue
        for (id_, _, _), embedding in zip(lot, embeddings):
            cur.execute("UPDATE articles SET embedding = %s WHERE id = %s", (embedding, id_))
        conn.commit()
        faits += len(lot)
        log.info(f"{faits}/{len(lignes)}")

    cur.close()
    conn.close()
    log.info(f"Terminé : {faits} embeddings régénérés")
    if faits < len(lignes):
        sys.exit(1)


if __name__ == "__main__":
    main()
