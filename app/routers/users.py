"""Routes d'administration des comptes utilisateurs."""

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_current_admin
from ..models import UserCreateRequest, UserInfo
from ..services import users
from ..services.users import User

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserInfo])
def list_users(current_admin: User = Depends(get_current_admin)):
    return users.list_users()


@router.post("", response_model=UserInfo, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreateRequest,
    current_admin: User = Depends(get_current_admin),
):
    if users.get_user(body.username) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ce nom d'utilisateur existe déjà",
        )
    users.save_user(body.username, body.role, body.password)
    return User(username=body.username, role=body.role, password_hash="")
