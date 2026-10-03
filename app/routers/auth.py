"""POST /login : vérifie les identifiants et retourne un jeton d'accès."""

from fastapi import APIRouter, HTTPException, Request, status

from .. import config, security
from ..models import LoginRequest, TokenResponse
from ..services import users
from ..services.login_guard import LoginGuard

router = APIRouter(tags=["auth"])
guard = LoginGuard()


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request) -> TokenResponse:
    client_ip = request.client.host if request.client else "inconnu"
    key = f"{client_ip}|{body.username.lower()}"

    if guard.is_blocked(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de tentatives. Réessayez dans une minute.",
            headers={"Retry-After": str(config.LOGIN_WINDOW_SECONDS)},
        )

    user = users.authenticate(body.username, body.password)
    if user is None:
        guard.register_failure(key)
        # Même message que l'utilisateur existe ou non.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants invalides",
            headers={"WWW-Authenticate": "Bearer"},
        )

    guard.reset(key)
    token, expires_in = security.create_access_token(user.username, user.role)
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        username=user.username,
        role=user.role,
    )
