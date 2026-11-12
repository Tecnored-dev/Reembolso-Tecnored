"""Painel de teste ("Ver como"): só admin, só com PAINEL_TESTE_ENABLED, nunca na main.

O admin continua logado na conta Microsoft dele; a sessão dele fica guardada
num segundo cookie (`session_admin`) e a sessão ativa passa a ser a do usuário
de teste. "Voltar" restaura a do admin. As rotas respondem 404 quando o painel
está desligado, para nem parecerem existir.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import sessoes
from app.auth.deps import definir_cookie, usuario_atual
from app.auth.papeis import papeis_publicos
from app.config import Settings, get_settings
from app.db import get_db
from app.services import painel_teste as painel
from app.storage import Armazenamento, get_armazenamento

router = APIRouter(prefix="/api/teste", tags=["teste"])


def _exigir_ligado(settings: Settings) -> None:
    if not settings.painel_teste_enabled or settings.app_env == "main":
        raise HTTPException(status_code=404)


def _admin_real(
    request: Request, db: Session, atual: sessoes.Usuario, settings: Settings
) -> sessoes.Usuario | None:
    """O admin de verdade: a sessão guardada (só durante o "ver como") ou a atual.

    O cookie do admin só vale enquanto a sessão ativa é de teste; fora disso um
    cookie esquecido no navegador (ex.: logout durante o "ver como") daria poder
    de admin a quem entrasse depois.
    """
    if atual.via == painel.VIA_TESTE:
        guardado = sessoes.obter_usuario(db, request.cookies.get(painel.COOKIE_ADMIN))
        return guardado if guardado and painel.eh_admin(guardado, settings) else None
    return atual if painel.eh_admin(atual, settings) else None


def _exigir_admin(
    request: Request, db: Session, atual: sessoes.Usuario, settings: Settings
) -> sessoes.Usuario:
    _exigir_ligado(settings)
    admin = _admin_real(request, db, atual, settings)
    if admin is None:
        raise HTTPException(status_code=403, detail="Só o admin usa o painel de teste.")
    return admin


@router.get("/estado")
def estado(
    request: Request,
    atual: sessoes.Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Sempre 200: o frontend usa para decidir se mostra o painel e a faixa."""
    if not settings.painel_teste_enabled or settings.app_env == "main":
        return {"ativo": False, "admin": False, "vendo_como": None, "usuarios": []}
    admin = _admin_real(request, db, atual, settings)
    vendo_como = None
    if atual.via == painel.VIA_TESTE and admin is not None:
        vendo_como = {
            "email": atual.email,
            "nome": atual.nome,
            "papeis": papeis_publicos(atual.papeis),
        }
    return {
        "ativo": True,
        "admin": admin is not None,
        "vendo_como": vendo_como,
        "usuarios": (
            [
                {
                    "chave": u.chave,
                    "email": u.email,
                    "nome": u.nome,
                    "papeis": papeis_publicos(u.papeis),
                    "descricao": u.descricao,
                }
                for u in painel.USUARIOS_TESTE
            ]
            if admin is not None
            else []
        ),
    }


class VerComo(BaseModel):
    email: str


@router.post("/ver-como")
def ver_como(
    entrada: VerComo,
    request: Request,
    response: Response,
    atual: sessoes.Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    _exigir_admin(request, db, atual, settings)
    alvo = painel.usuario_teste(entrada.email)
    if alvo is None:
        raise HTTPException(status_code=400, detail="Usuário de teste inválido.")
    # Guarda a sessão do admin só na primeira troca; trocar de novo mantém a original.
    token_admin = request.cookies.get(painel.COOKIE_ADMIN)
    ja_vendo_como = (
        atual.via == painel.VIA_TESTE
        and token_admin
        and sessoes.obter_usuario(db, token_admin) is not None
    )
    if not ja_vendo_como:
        token_admin = request.cookies.get(sessoes.COOKIE)
        response.set_cookie(
            painel.COOKIE_ADMIN,
            token_admin or "",
            httponly=True,
            samesite="lax",
            secure=settings.app_env != "local",
            max_age=int(sessoes.DURACAO.total_seconds()),
        )
    else:
        # Já estava vendo como outro: encerra essa sessão de teste.
        sessoes.encerrar_sessao(db, request.cookies.get(sessoes.COOKIE))
    token = sessoes.criar_sessao(
        db,
        email=alvo.email,
        nome=alvo.nome,
        grupos=[],
        papeis=list(alvo.papeis),
        via=painel.VIA_TESTE,
    )
    painel.garantir_cadastros(db)
    db.commit()
    definir_cookie(response, token, settings)
    return {"vendo_como": alvo.nome}


@router.post("/voltar")
def voltar(
    request: Request,
    response: Response,
    atual: sessoes.Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    _exigir_ligado(settings)
    token_admin = request.cookies.get(painel.COOKIE_ADMIN)
    admin = sessoes.obter_usuario(db, token_admin)
    if atual.via != painel.VIA_TESTE or admin is None or not painel.eh_admin(admin, settings):
        raise HTTPException(status_code=400, detail="Você não está vendo como outro usuário.")
    sessoes.encerrar_sessao(db, request.cookies.get(sessoes.COOKIE))
    definir_cookie(response, token_admin or "", settings)
    response.delete_cookie(painel.COOKIE_ADMIN)
    return {"ok": True}


@router.post("/demo", status_code=201)
def demo(
    request: Request,
    atual: sessoes.Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    armazenamento: Armazenamento = Depends(get_armazenamento),
):
    _exigir_admin(request, db, atual, settings)
    criados = painel.criar_demo(db, settings, armazenamento)
    return {"criados": [s.codigo for s in criados]}


@router.post("/limpar")
def limpar(
    request: Request,
    atual: sessoes.Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    armazenamento: Armazenamento = Depends(get_armazenamento),
):
    _exigir_admin(request, db, atual, settings)
    return {"apagados": painel.limpar(db, armazenamento)}
