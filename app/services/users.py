"""Accès aux utilisateurs, stockés dans data/users.json.

Format du fichier :
    {"users": [{"username": "alice", "role": "user", "password_hash": "scrypt$..."}]}
"""

import json
import secrets
from dataclasses import dataclass

from .. import config
from ..security import hash_password, needs_rehash, verify_password

VALID_ROLES = ("user", "admin")

# Hash factice : permet de dépenser le même temps de calcul quand l'utilisateur
# n'existe pas, pour ne pas révéler par le temps de réponse quels comptes existent.
_DUMMY_HASH = hash_password(secrets.token_hex(16))


@dataclass(frozen=True)
class User:
    username: str
    role: str
    password_hash: str


def _load_users() -> dict[str, User]:
    try:
        raw = json.loads(config.USERS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    users: dict[str, User] = {}
    for item in raw.get("users", []):
        if item.get("role") not in VALID_ROLES:
            continue
        users[item["username"]] = User(
            username=item["username"],
            role=item["role"],
            password_hash=item["password_hash"],
        )
    return users


def get_user(username: str) -> User | None:
    return _load_users().get(username)


def list_users() -> list[User]:
    return list(_load_users().values())


def authenticate(username: str, password: str) -> User | None:
    """Retourne l'utilisateur si les identifiants sont corrects, sinon None."""
    user = get_user(username)
    stored = user.password_hash if user else _DUMMY_HASH
    password_ok = verify_password(password, stored)
    if user is None or not password_ok:
        return None
    if needs_rehash(user.password_hash):
        save_user(user.username, user.role, password)
    return user


def save_user(username: str, role: str, password: str) -> None:
    """Crée ou remplace un utilisateur (utilisé par scripts/create_user.py)."""
    if role not in VALID_ROLES:
        raise ValueError(f"Rôle invalide : {role}")
    users = _load_users()
    users[username] = User(username, role, hash_password(password))
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "users": [
            {"username": u.username, "role": u.role, "password_hash": u.password_hash}
            for u in users.values()
        ]
    }
    config.USERS_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
