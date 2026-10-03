"""Stockage des fichiers sur disque et index des propriétaires.

Ce module ne connaît ni FastAPI ni HTTP. Il lève des exceptions métier que les
routeurs traduisent en codes de statut.

Sécurité du nom de fichier (anti path traversal) :
  - à l'upload, on ne garde que le dernier segment du nom et on remplace les
    caractères non autorisés ;
  - pour les noms reçus dans l'URL, on exige qu'ils soient déjà "propres" ;
  - dans tous les cas, le chemin résolu doit rester directement dans le dossier
    de stockage (cela bloque aussi les liens symboliques sortants).
"""

import json
import os
import re
import secrets
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from .. import config

MAX_NAME_LENGTH = 200
_FORBIDDEN_CHARS = re.compile(r"[^\w.\- ()]", re.UNICODE)
_meta_lock = threading.Lock()


class StorageError(Exception):
    """Base des erreurs de stockage."""


class InvalidFilename(StorageError):
    pass


class FileNotFound(StorageError):
    pass


class FileAlreadyExists(StorageError):
    pass


class FileTooLarge(StorageError):
    pass


# --- Noms et chemins --------------------------------------------------------


def sanitize_filename(raw: str | None) -> str:
    """Transforme un nom fourni par un client en nom sûr, ou lève InvalidFilename."""
    if not raw:
        raise InvalidFilename("Nom de fichier manquant")
    name = raw.replace("\\", "/").split("/")[-1]
    name = unicodedata.normalize("NFC", name)
    name = _FORBIDDEN_CHARS.sub("_", name).strip().lstrip(".")
    if not name or len(name) > MAX_NAME_LENGTH:
        raise InvalidFilename("Nom de fichier invalide")
    return name


def validate_name(name: str) -> str:
    """Pour un nom venant de l'URL : il doit être identique à sa version nettoyée."""
    if sanitize_filename(name) != name:
        raise InvalidFilename("Nom de fichier invalide")
    return name


def _path_for(name: str) -> Path:
    validate_name(name)
    root = config.STORAGE_DIR.resolve()
    path = (root / name).resolve()
    if path.parent != root:
        raise InvalidFilename("Nom de fichier invalide")
    return path


# --- Index des propriétaires (data/files_meta.json) -------------------------


def _read_meta() -> dict:
    try:
        return json.loads(config.META_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_meta(meta: dict) -> None:
    config.META_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = config.META_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, config.META_FILE)


def get_owner(name: str) -> str | None:
    return _read_meta().get(name, {}).get("owner")


# --- Opérations -------------------------------------------------------------


def _info_for(path: Path, meta: dict) -> dict:
    stat = path.stat()
    return {
        "name": path.name,
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        "owner": meta.get(path.name, {}).get("owner"),
    }


def list_files() -> list[dict]:
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    meta = _read_meta()
    entries = sorted(config.STORAGE_DIR.iterdir(), key=lambda p: p.name.lower())
    return [
        _info_for(p, meta)
        for p in entries
        if p.is_file() and not p.is_symlink() and not p.name.startswith(".")
    ]


def get_info(name: str) -> dict:
    path = get_path(name)
    return _info_for(path, _read_meta())


def get_path(name: str) -> Path:
    path = _path_for(name)
    if not path.is_file():
        raise FileNotFound(name)
    return path


async def save_file(filename: str | None, owner: str, source, max_bytes: int) -> str:
    """Enregistre un fichier envoyé. `source` doit avoir `async read(taille)`.

    L'écriture passe par un fichier temporaire, puis un lien dur atomique :
    deux envois simultanés du même nom ne peuvent pas s'écraser.
    """
    name = sanitize_filename(filename)
    final = _path_for(name)
    if final.exists():
        raise FileAlreadyExists(name)

    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = final.parent / f".upload-{secrets.token_hex(8)}.tmp"
    size = 0
    try:
        with open(tmp, "wb") as out:
            while chunk := await source.read(config.UPLOAD_CHUNK_BYTES):
                size += len(chunk)
                if size > max_bytes:
                    raise FileTooLarge(name)
                out.write(chunk)
        try:
            os.link(tmp, final)
        except FileExistsError:
            raise FileAlreadyExists(name) from None
    finally:
        tmp.unlink(missing_ok=True)

    with _meta_lock:
        meta = _read_meta()
        meta[name] = {
            "owner": owner,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_meta(meta)
    return name


def delete_file(name: str) -> None:
    path = get_path(name)
    path.unlink()
    with _meta_lock:
        meta = _read_meta()
        if meta.pop(name, None) is not None:
            _write_meta(meta)
