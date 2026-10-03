"""Crée ou met à jour un utilisateur dans data/users.json.

Usage :
    python -m scripts.create_user alice --role user
    python -m scripts.create_user admin --role admin

Le mot de passe est demandé de façon interactive (non affiché), puis haché
avec scrypt avant d'être écrit : il n'est jamais stocké en clair.
"""

import argparse
import getpass
import sys

from app.services import users


def main() -> int:
    parser = argparse.ArgumentParser(description="Créer ou modifier un utilisateur")
    parser.add_argument("username")
    parser.add_argument("--role", choices=users.VALID_ROLES, default="user")
    parser.add_argument(
        "--password",
        help="À éviter : le mot de passe resterait dans l'historique du shell",
    )
    args = parser.parse_args()

    password = args.password or getpass.getpass("Mot de passe : ")
    if len(password) < 8:
        print("Le mot de passe doit contenir au moins 8 caractères.", file=sys.stderr)
        return 1

    users.save_user(args.username, args.role, password)
    print(f"Utilisateur '{args.username}' ({args.role}) enregistré.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
