"""Schémas Pydantic : structure des requêtes, des réponses et des événements."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Durée de validité du jeton, en secondes")
    username: str
    role: Literal["user", "admin"]


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=256)
    role: Literal["user", "admin"] = "user"


class UserInfo(BaseModel):
    username: str
    role: Literal["user", "admin"]


class FileInfo(BaseModel):
    name: str
    size: int = Field(description="Taille en octets")
    modified: datetime = Field(description="Date de dernière modification (UTC)")
    owner: str | None = Field(description="Utilisateur qui a déposé le fichier")


class FileEvent(BaseModel):
    """Message JSON diffusé à tous les clients WebSocket."""

    event: Literal["uploaded", "deleted"]
    file: str
    user: str
