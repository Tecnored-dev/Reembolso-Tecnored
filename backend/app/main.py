"""Aplicação FastAPI — monta rotas, CORS e docs."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, sistema
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    settings.validar()

    app = FastAPI(
        title="Reembolso-Tecnored — API",
        docs_url="/docs" if settings.enable_api_docs else None,
        redoc_url="/redoc" if settings.enable_api_docs else None,
        openapi_url="/openapi.json" if settings.enable_api_docs else None,
    )
    # Frontend em outra origem: CORS com credenciais para o cookie de sessão.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(sistema.router)
    app.include_router(auth.router)
    return app


app = create_app()
