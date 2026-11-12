"""Aplicação FastAPI — monta rotas, CORS, docs, erros e tarefas periódicas."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import logs
from app.api.routes import auth, cadastros, comprovantes, sistema, solicitacoes, teste
from app.config import get_settings
from app.services.erros import NaoEncontrado, RegraNegocio, SemPermissao

log = logging.getLogger(__name__)

INTERVALO_TAREFAS_SEGUNDOS = 3600


def _rodar_expiracao() -> None:
    from app.db import get_db
    from app.services.fluxo import processar_expiracoes

    gerador = get_db()
    db = next(gerador)
    try:
        processar_expiracoes(db, get_settings())
    finally:
        gerador.close()


async def _tarefas_periodicas() -> None:
    while True:
        try:
            await asyncio.to_thread(_rodar_expiracao)
        except Exception:  # nunca derrubar a API por causa da tarefa
            log.exception("Falha na tarefa de expiração.")
        await asyncio.sleep(INTERVALO_TAREFAS_SEGUNDOS)


@contextlib.asynccontextmanager
async def _ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    tarefa = None
    if get_settings().tarefas_automaticas:
        tarefa = asyncio.create_task(_tarefas_periodicas())
    yield
    if tarefa:
        tarefa.cancel()


def create_app() -> FastAPI:
    settings = get_settings()
    settings.validar()
    logs.instalar()

    app = FastAPI(
        title="Reembolso-Tecnored — API",
        docs_url="/docs" if settings.enable_api_docs else None,
        redoc_url="/redoc" if settings.enable_api_docs else None,
        openapi_url="/openapi.json" if settings.enable_api_docs else None,
        lifespan=_ciclo_de_vida,
    )
    # Frontend em outra origem: CORS com credenciais para o cookie de sessão.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RegraNegocio)
    async def _regra(_: Request, exc: RegraNegocio):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(SemPermissao)
    async def _permissao(_: Request, exc: SemPermissao):
        return JSONResponse(status_code=403, content={"detail": str(exc) or "Sem permissão."})

    @app.exception_handler(NaoEncontrado)
    async def _nao_encontrado(_: Request, exc: NaoEncontrado):
        return JSONResponse(status_code=404, content={"detail": "Solicitação não encontrada."})

    app.include_router(sistema.router)
    app.include_router(auth.router)
    app.include_router(cadastros.router)
    app.include_router(solicitacoes.router)
    app.include_router(comprovantes.router)
    app.include_router(teste.router)
    app.include_router(solicitacoes.tarefas)
    return app


app = create_app()
