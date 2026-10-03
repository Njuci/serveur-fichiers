"""Routes /files : lister, téléverser, télécharger, supprimer.

Le routeur ne fait que du HTTP : il appelle le service de stockage, traduit ses
erreurs en codes de statut, puis demande au notifier de prévenir les clients.
"""

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse

from .. import config
from ..dependencies import can_delete, get_current_user
from ..models import FileEvent, FileInfo
from ..services import storage
from ..services.notifier import notifier
from ..services.users import User

router = APIRouter(prefix="/files", tags=["files"])


@router.get("", response_model=list[FileInfo])
def list_files(user: User = Depends(get_current_user)):
    return storage.list_files()


@router.post("", response_model=FileInfo, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    try:
        name = await storage.save_file(
            file.filename, user.username, file, config.MAX_UPLOAD_BYTES
        )
    except storage.InvalidFilename as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except storage.FileAlreadyExists:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Un fichier de ce nom existe déjà"
        )
    except storage.FileTooLarge:
        limit_mb = config.MAX_UPLOAD_BYTES // (1024 * 1024)
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Fichier trop volumineux (maximum {limit_mb} Mo)",
        )

    await notifier.broadcast(
        FileEvent(event="uploaded", file=name, user=user.username).model_dump()
    )
    return storage.get_info(name)


@router.get("/{name}")
def download_file(name: str, user: User = Depends(get_current_user)):
    try:
        path = storage.get_path(name)
    except storage.InvalidFilename as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except storage.FileNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Fichier introuvable")
    # application/octet-stream + attachment : le navigateur télécharge au lieu
    # d'interpréter le contenu (pas d'exécution de HTML ou de script envoyé).
    return FileResponse(path, filename=name, media_type="application/octet-stream")


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(name: str, user: User = Depends(get_current_user)):
    try:
        storage.get_path(name)
    except storage.InvalidFilename as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except storage.FileNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Fichier introuvable")

    if not can_delete(user, storage.get_owner(name)):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Seul le propriétaire ou un administrateur peut supprimer ce fichier",
        )

    try:
        storage.delete_file(name)
    except storage.FileNotFound:  # supprimé entre-temps par quelqu'un d'autre
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Fichier introuvable")

    await notifier.broadcast(
        FileEvent(event="deleted", file=name, user=user.username).model_dump()
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
