"""Primitives de sécurité : hachage des mots de passe et jetons JWT.

Ce module ne connaît ni FastAPI ni HTTP : il ne fait que hacher, vérifier,
signer et décoder.
"""

import base64
import hashlib
import hmac
import os
import time

import jwt

from . import config

# Paramètres scrypt (coût mémoire ~16 Mio, ~50 ms par hachage).
_N, _R, _P = 2**14, 8, 1
_DKLEN = 32
_MAX_SCRYPT_N = 2**20


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str) -> str:
    """Retourne 'scrypt$N$r$p$sel$hash' (sel aléatoire unique par mot de passe)."""
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN
    )
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """Compare en temps constant. Retourne False si le format stocké est invalide."""
    try:
        algo, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        n, r, p = int(n), int(r), int(p)
        if n < 2 or n > _MAX_SCRYPT_N or n & (n - 1) or r < 1 or p < 1:
            return False
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(hash_b64, validate=True)
        if len(salt) < 16 or not 16 <= len(expected) <= 64:
            return False
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
        )
    except (ValueError, TypeError, OverflowError, MemoryError):
        return False
    return hmac.compare_digest(candidate, expected)


def needs_rehash(stored: str) -> bool:
    """Indique si un hash valide n'utilise plus les paramètres actuels."""
    try:
        algo, n, r, p, salt_b64, hash_b64 = stored.split("$")
        return (
            algo != "scrypt"
            or int(n) != _N
            or int(r) != _R
            or int(p) != _P
            or len(base64.b64decode(salt_b64, validate=True)) != 16
            or len(base64.b64decode(hash_b64, validate=True)) != _DKLEN
        )
    except (ValueError, TypeError):
        return True


def create_access_token(username: str, role: str) -> tuple[str, int]:
    """Signe un JWT. Retourne (jeton, durée de validité en secondes)."""
    now = int(time.time())
    expires_in = config.JWT_EXPIRE_MINUTES * 60
    payload = {"sub": username, "role": role, "iat": now, "exp": now + expires_in}
    token = jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)
    return token, expires_in


def decode_access_token(token: str) -> dict | None:
    """Retourne les claims si le jeton est valide et non expiré, sinon None.

    La liste `algorithms` est fixée côté serveur : un jeton signé avec un autre
    algorithme (ou 'none') est rejeté.
    """
    try:
        return jwt.decode(
            token,
            config.JWT_SECRET,
            algorithms=[config.JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        return None
