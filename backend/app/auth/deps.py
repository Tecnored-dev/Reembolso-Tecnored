"""Dependências de rota: sessão atual e exigência de papel."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.auth import sessoes
from app.auth.cloudflare import identidade_cloudflare
from app.auth.papeis import resolver_papeis
from app.config import Settings, get_settings
from app.db import get_db


def definir_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        sessoes.COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.app_env != "local",
        max_age=int(sessoes.DURACAO.total_seconds()),
    )


async def usuario_opcional(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> sessoes.Usuario | None:
    """Sessão do cookie; sem cookie, tenta o SSO do Cloudflare Access."""
    usuario = sessoes.obter_usuario(db, request.cookies.get(sessoes.COOKIE))
    if usuario and usuario.via == "teste" and not settings.painel_teste_enabled:
        # Painel desligado: sessões "Ver como" que ainda estavam abertas param de valer.
        usuario = None
    if usuario:
        return usuario

    identidade = await identidade_cloudflare(request, settings)
    email = (identidade or {}).get("email")
    if not email:
        return None
    grupos = [g["id"] for g in (identidade.get("groups") or []) if g.get("id")]
    papeis = resolver_papeis(grupos, settings)
    token = sessoes.criar_sessao(
        db,
        email=email,
        nome=identidade.get("name") or email,
        grupos=grupos,
        papeis=papeis,
        via="cloudflare",
    )
    definir_cookie(response, token, settings)
    return sessoes.obter_usuario(db, token)


def usuario_atual(
    usuario: sessoes.Usuario | None = Depends(usuario_opcional),
) -> sessoes.Usuario:
    if usuario is None:
        raise HTTPException(status_code=401, detail="Não autenticado")
    return usuario


def exigir_papel(papel: str):
    def _dep(usuario: sessoes.Usuario = Depends(usuario_atual)) -> sessoes.Usuario:
        if not usuario.tem(papel):
            raise HTTPException(status_code=403, detail=f"Acesso restrito ({papel}).")
        return usuario

    return _dep
