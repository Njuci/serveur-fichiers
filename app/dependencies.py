"""Dépendances FastAPI : qui fait la requête, et a-t-il le droit ?"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .security import decode_access_token
from .services import users
from .services.users import User

bearer_scheme = HTTPBearer(auto_error=False)


def user_from_token(token: str) -> User | None:
    """Retourne l'utilisateur correspondant à un jeton valide, sinon None.

    Le rôle est relu dans users.json (et non dans le jeton) : supprimer ou
    rétrograder un compte prend effet immédiatement.
    """
    claims = decode_access_token(token)
    if claims is None:
        return None
    return users.get_user(claims["sub"])


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User:
    user = user_from_token(credentials.credentials) if credentials else None
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise ou jeton invalide",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def can_delete(user: User, owner: str | None) -> bool:
    """Propriétaire du fichier, ou administrateur. Un fichier sans propriétaire
    connu (déposé hors de l'API) n'est supprimable que par un administrateur."""
    return user.role == "admin" or (owner is not None and owner == user.username)


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs",
        )
    return user
