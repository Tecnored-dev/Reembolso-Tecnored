"""Login (Azure AD / OIDC), callback, logout e login de desenvolvimento.

Rotas de navegação de página inteira (redirects) — o frontend aponta para
elas com <a href>, nunca via axios (fluxo OAuth). Portado do Hello-World,
trocando a sessão em memória pela sessão persistida no banco.
"""

from __future__ import annotations

import asyncio
import secrets
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from msal import ConfidentialClientApplication
from sqlalchemy.orm import Session

from app.auth import sessoes
from app.auth.deps import definir_cookie
from app.auth.papeis import PAPEIS_ESPECIAIS, resolver_papeis
from app.config import Settings, get_settings
from app.db import get_db
from app.services import gestores
from app.services.painel_teste import COOKIE_ADMIN

router = APIRouter(tags=["auth"])

SCOPES = ["GroupMember.Read.All"]  # openid/profile/email são geridos pelo MSAL

# Proteção contra CSRF no login (parâmetro `state` do OAuth): o /login sorteia
# um valor, guarda num cookie curto e manda para a Microsoft; o callback só
# aceita a volta se o valor que a Microsoft devolveu for o mesmo do cookie.
# Sem isso, alguém poderia fazer o navegador da vítima "logar" com o código
# de outra conta.
COOKIE_STATE = "oauth_state"
STATE_VALIDADE_SEGUNDOS = 600


def _erro_login(settings: Settings, motivo: str) -> RedirectResponse:
    resposta = RedirectResponse(f"{settings.frontend_url}/?auth_error={quote(motivo[:60])}")
    resposta.delete_cookie(COOKIE_STATE, path="/auth/callback")
    return resposta


def _msal(settings: Settings) -> ConfidentialClientApplication:
    return ConfidentialClientApplication(
        settings.azure_client_id,
        authority=f"https://login.microsoftonline.com/{settings.azure_tenant_id}",
        client_credential=settings.azure_client_secret,
    )


@router.get("/login")
def login(settings: Settings = Depends(get_settings)):
    if not settings.azure_configurado:
        return RedirectResponse(f"{settings.frontend_url}/?auth_error=azure_nao_configurado")
    state = secrets.token_urlsafe(32)
    url = _msal(settings).get_authorization_request_url(
        scopes=SCOPES,
        redirect_uri=settings.azure_redirect_uri,
        prompt=settings.azure_login_prompt or None,
        state=state,
    )
    resposta = RedirectResponse(url)
    resposta.set_cookie(
        COOKIE_STATE,
        state,
        max_age=STATE_VALIDADE_SEGUNDOS,
        httponly=True,
        # Lax: o cookie volta na navegação de topo vinda da Microsoft (GET).
        samesite="lax",
        secure=settings.app_env != "local",
        path="/auth/callback",
    )
    return resposta


@router.get("/auth/callback")
async def auth_callback(
    code: str | None = None,
    error: str | None = None,
    state: str | None = None,
    oauth_state: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if error or not code or not settings.azure_configurado:
        return _erro_login(settings, error or "unknown")
    if not (state and oauth_state and secrets.compare_digest(state, oauth_state)):
        return _erro_login(settings, "state_invalido")

    result = _msal(settings).acquire_token_by_authorization_code(
        code=code, scopes=SCOPES, redirect_uri=settings.azure_redirect_uri
    )
    if "error" in result:
        return _erro_login(settings, str(result.get("error")))

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://graph.microsoft.com/v1.0/me/memberOf",
            headers={"Authorization": f"Bearer {result['access_token']}"},
            timeout=10.0,
        )
    grupos = [g["id"] for g in resp.json().get("value", []) if g.get("id")]

    # Aproveita o token de quem está logando para atualizar a lista de gestores
    # (permissão delegada: só dá para ler o grupo em nome de alguém logado).
    await asyncio.to_thread(
        gestores.sincronizar_no_login, db, settings, result["access_token"], sessoes.agora_utc()
    )

    claims = result.get("id_token_claims", {})
    email = claims.get("preferred_username", "")
    nome = claims.get("name") or email or "Desconhecido"
    token = sessoes.criar_sessao(
        db,
        email=email,
        nome=nome,
        grupos=grupos,
        papeis=resolver_papeis(grupos, settings),
        via="microsoft",
    )
    response = RedirectResponse(f"{settings.frontend_url}/inicio", status_code=302)
    definir_cookie(response, token, settings)
    response.delete_cookie(COOKIE_STATE, path="/auth/callback")
    return response


@router.get("/logout")
def logout(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    via = sessoes.encerrar_sessao(db, request.cookies.get(sessoes.COOKIE))
    # Saiu durante o "ver como" do painel de teste: encerra também a sessão do admin
    # guardada e apaga o cookie, para ninguém herdar o poder de admin.
    sessoes.encerrar_sessao(db, request.cookies.get(COOKIE_ADMIN))
    destino = (
        f"https://{settings.cf_access_team_domain}/cdn-cgi/access/logout"
        if via == "cloudflare" and settings.cf_access_team_domain
        else settings.frontend_url
    )
    response = RedirectResponse(destino, status_code=302)
    response.delete_cookie(sessoes.COOKIE)
    response.delete_cookie(COOKIE_ADMIN)
    return response


@router.get("/dev/login", include_in_schema=False)
def dev_login(
    email: str = "dev@tecnored.com.br",
    nome: str = "Dev Local",
    papeis: str = "",
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Login SEM Microsoft, só em APP_ENV=local com DEV_LOGIN_ENABLED=true.

    Existe para dar para trabalhar antes do App Registration ficar pronto e
    para testar cada papel: /dev/login?email=gestor@x&papeis=gestor.
    Em hml/main a API nem sobe com isso ligado (Settings.validar).
    """
    if not (settings.dev_login_enabled and settings.app_env == "local"):
        raise HTTPException(status_code=404)
    escolhidos = [p for p in papeis.split(",") if p in PAPEIS_ESPECIAIS]
    token = sessoes.criar_sessao(
        db, email=email, nome=nome, grupos=[], papeis=escolhidos, via="dev"
    )
    response = RedirectResponse(f"{settings.frontend_url}/inicio", status_code=302)
    definir_cookie(response, token, settings)
    return response
