from traitements.bdd.connexion import get_connection


def enregistrement_resumes(resumes: list[dict]) -> None:
    """
    Sauvegarde une liste de résumés en BDD.
    resumes : list[dict] — chaque dict { cluster_id, titre, resume, cluster_id_fk (optionnel) }
    """
    if not resumes:
        return

    conn = get_connection()
    cursor = conn.cursor()
    try:
        for r in resumes:
            cursor.execute(
                """
                INSERT INTO resumes (cluster_id, titre, resume, cluster_id_fk)
                VALUES (%s, %s, %s, %s)
                """,
                (r["cluster_id"], r["titre"], r["resume"], r.get("cluster_id_fk")),
            )
        conn.commit()
        print(f"[+] {len(resumes)} résumés sauvegardés en BDD")
    except Exception as e:
        print(f"[!] Erreur sauvegarde résumés : {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()