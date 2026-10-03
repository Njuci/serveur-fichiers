"""Point d'entrée : assemble l'application, sans logique métier."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .dependencies import user_from_token
from .routers import auth, files, users, ws

# La CSP n'est appliquée qu'à la page client : l'interface /docs (Swagger) a
# besoin de scripts externes qu'elle bloquerait.
PAGE_CSP = (
    "default-src 'self'; connect-src 'self' ws: wss:; img-src 'self' data:; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
UPLOAD_OVERHEAD_BYTES = 1024 * 1024  # marge pour l'enveloppe multipart


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="Serveur de fichiers interne",
    description="Dépôt de fichiers authentifié avec notifications WebSocket.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def protect_uploads_and_set_headers(request: Request, call_next):
    # Rejeter tôt un envoi non authentifié ou trop gros, avant que le corps
    # multipart ne soit lu et écrit sur disque.
    if request.method == "POST" and request.url.path == "/files":
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or user_from_token(token) is None:
            return JSONResponse(
                {"detail": "Authentification requise ou jeton invalide"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > config.MAX_UPLOAD_BYTES + UPLOAD_OVERHEAD_BYTES:
            return JSONResponse({"detail": "Fichier trop volumineux"}, status_code=413)

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    path = request.url.path
    if path in ("/", "/app") or path.startswith("/static"):
        response.headers["Content-Security-Policy"] = PAGE_CSP
        response.headers["X-Frame-Options"] = "DENY"
    return response


app.include_router(auth.router)
app.include_router(files.router)
app.include_router(users.router)
app.include_router(ws.router)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(config.STATIC_DIR / "login.html")


@app.get("/app", include_in_schema=False)
def application():
    return FileResponse(config.STATIC_DIR / "app.html")


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
