from pathlib import Path

DOSSIER_SOURCE = Path("traitements")
FICHIER_SORTIE = Path("contenu_traitements.txt")

# --- CONFIGURATION DES EXCLUSIONS ---
# Dossiers à ignorer
DOSSIERS_EXCLUS = {"__pycache__", "venv", ".git", ".vscode", ".env", "README.md", "contenuProjet.py"}

# Noms de fichiers exacts à ignorer
FICHIERS_EXCLUS = {
    ".DS_Store",
    "contenu_traitements.txt",
    "secret.env",
}

# Extensions à ignorer (en minuscules, avec le point)
EXTENSIONS_EXCLUES = {
    ".pyc",
    ".png",
    ".jpg",
    ".exe",
    ".zip",
    ".log",
}
# ------------------------------------

with open(FICHIER_SORTIE, "w", encoding="utf-8") as sortie:
    for fichier in DOSSIER_SOURCE.rglob("*"):
        # Ignorer si ce n'est pas un fichier
        if not fichier.is_file():
            continue

        # Ignorer si le fichier est dans un dossier exclu
        if any(dossier in fichier.parts for dossier in DOSSIERS_EXCLUS):
            continue

        # Ignorer par nom exact
        if fichier.name in FICHIERS_EXCLUS:
            continue

        # Ignorer par extension
        if fichier.suffix.lower() in EXTENSIONS_EXCLUES:
            continue

        try:
            contenu = fichier.read_text(encoding="utf-8")

            sortie.write("=" * 80 + "\n")
            sortie.write(f"FICHIER : {fichier}\n")
            sortie.write("=" * 80 + "\n\n")
            sortie.write(contenu)
            sortie.write("\n\n\n")

        except Exception as e:
            sortie.write("=" * 80 + "\n")
            sortie.write(f"FICHIER : {fichier}\n")
            sortie.write("=" * 80 + "\n\n")
            sortie.write(f"Erreur de lecture : {e}\n\n\n")

print(f"Export terminé : {FICHIER_SORTIE}")