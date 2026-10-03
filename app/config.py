"""Configuration centralisée : chemins, durée des jetons, limites.

Tout ce qui est sensible (le secret JWT) vient de variables d'environnement,
jamais du code source.
"""

import logging
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# DATA_DIR et STORAGE_DIR peuvent être redirigés vers un disque persistant
# lors du déploiement (ex. un volume monté sur /var/data).
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
STORAGE_DIR = Path(os.environ.get("STORAGE_DIR", BASE_DIR / "storage"))
STATIC_DIR = BASE_DIR / "static"

USERS_FILE = DATA_DIR / "users.json"
META_FILE = DATA_DIR / "files_meta.json"

# --- Jetons JWT -------------------------------------------------------------
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "30"))

JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    # Pratique en développement, mais à éviter en production : un secret
    # aléatoire change à chaque démarrage et invalide tous les jetons.
    JWT_SECRET = secrets.token_urlsafe(48)
    logging.getLogger("uvicorn.error").warning(
        "JWT_SECRET non défini : un secret aléatoire a été généré. "
        "Les jetons seront invalides après un redémarrage."
    )

# --- Fichiers ---------------------------------------------------------------
MAX_UPLOAD_BYTES = int(float(os.environ.get("MAX_UPLOAD_MB", "10")) * 1024 * 1024)
UPLOAD_CHUNK_BYTES = 64 * 1024

# --- Protection contre le brute-force sur /login ----------------------------
LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW_SECONDS = 60
