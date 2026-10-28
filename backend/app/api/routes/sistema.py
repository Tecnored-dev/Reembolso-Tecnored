"""Health check, configuração pública e sessão atual."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.routes.comprovantes import get_motor
from app.auth.deps import usuario_atual
from app.auth.papeis import papeis_publicos
from app.auth.sessoes import Usuario
from app.config import (
    APP_COMMIT_HASH,
    APP_RELEASE_DATE,
    APP_TITLE,
    APP_VERSION,
    APP_WELCOME_MESSAGE,
    Settings,
    get_settings,
)
from app.db import banco_ok
from app.ocr.motor import MotorOcr
from app.storage import get_armazenamento

router = APIRouter()


@router.get("/health", include_in_schema=False)
def health():
    """Healthcheck do Docker: banco e armazenamento de arquivos respondendo."""
    problemas = []
    if not banco_ok():
        problemas.append("database")
    if not get_armazenamento().saudavel():
        problemas.append("storage")
    if problemas:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "reason": problemas})
    return {"status": "ok"}


@router.get("/api/config")
def config(settings: Settings = Depends(get_settings), motor: MotorOcr = Depends(get_motor)):
    return {
        "title": APP_TITLE,
        "welcome_msg": APP_WELCOME_MESSAGE,
        "bg_color": settings.app_bg_color,
        "env": settings.app_env,
        "version": APP_VERSION,
        "released_at": APP_RELEASE_DATE,
        "commit_hash": APP_COMMIT_HASH,
        "login_microsoft": settings.azure_configurado,
        "login_dev": settings.dev_login_enabled and settings.app_env == "local",
        # Leitura automática de comprovantes (POST /api/comprovantes/analisar).
        "leitura_comprovante": motor.disponivel(),
    }


@router.get("/api/session")
def session(usuario: Usuario = Depends(usuario_atual)):
    return {
        "name": usuario.nome,
        "email": usuario.email,
        "papeis": papeis_publicos(usuario.papeis),
        "login_method": usuario.via,
    }
