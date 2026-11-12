"""Login: proteção do `state` (CSRF no OAuth) e código fora do log."""

from __future__ import annotations

import dataclasses
import logging
from urllib.parse import parse_qs, urlparse

import pytest

from app.logs import OcultarQuerySensivel


@pytest.fixture
def azure(cliente, settings, monkeypatch):
    """Azure 'configurado', com MSAL e Graph falsos (sem rede)."""
    from app.api.routes import auth
    from app.config import get_settings
    from app.main import app

    com_azure = dataclasses.replace(
        settings, azure_client_id="id", azure_client_secret="s", azure_tenant_id="t"
    )
    app.dependency_overrides[get_settings] = lambda: com_azure
    chamadas = []

    class MsalFalso:
        def get_authorization_request_url(self, scopes, redirect_uri, prompt, state):
            return f"https://login.microsoftonline.com/authorize?state={state}"

        def acquire_token_by_authorization_code(self, **kw):
            chamadas.append(kw)
            return {
                "access_token": "tk",
                "id_token_claims": {"preferred_username": "colab@t.com", "name": "Colab"},
            }

    class Resp:
        status_code = 200

        def json(self):
            return {"value": []}

    class ClienteFalso:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return Resp()

    monkeypatch.setattr(auth, "_msal", lambda s: MsalFalso())
    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **k: ClienteFalso())
    monkeypatch.setattr(auth.gestores, "sincronizar_no_login", lambda *a: False)
    return chamadas


def _state_do_login(cliente) -> str:
    r = cliente.get("/login")
    assert r.status_code == 307
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    cookie = r.headers["set-cookie"]
    assert f"oauth_state={state}" in cookie
    assert "HttpOnly" in cookie and "Path=/auth/callback" in cookie
    return state


def test_login_manda_state_e_guarda_no_cookie(cliente, azure):
    assert len(_state_do_login(cliente)) >= 40


def test_callback_com_state_certo_entra(cliente, azure):
    state = _state_do_login(cliente)
    r = cliente.get("/auth/callback", params={"code": "abc", "state": state})
    assert r.status_code == 302 and r.headers["location"].endswith("/inicio")
    assert len(azure) == 1


def test_callback_sem_cookie_e_recusado(cliente, azure):
    r = cliente.get("/auth/callback", params={"code": "abc", "state": "qualquer"})
    assert "auth_error=state_invalido" in r.headers["location"]
    assert azure == []  # nem troca o código por token


def test_callback_com_state_diferente_e_recusado(cliente, azure):
    _state_do_login(cliente)
    r = cliente.get("/auth/callback", params={"code": "abc", "state": "outro"})
    assert "auth_error=state_invalido" in r.headers["location"]
    assert azure == []


def test_erro_vindo_da_microsoft_e_escapado(cliente, azure):
    r = cliente.get("/auth/callback", params={"error": "x&y=<script>"})
    assert r.headers["location"].endswith("?auth_error=x%26y%3D%3Cscript%3E")


def _registro(caminho: str) -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:5", "GET", caminho, "1.1", 302),
        None,
    )


def test_log_esconde_o_codigo_do_callback():
    rec = _registro("/auth/callback?code=SEGREDO&session_state=x")
    OcultarQuerySensivel().filter(rec)
    assert "SEGREDO" not in rec.getMessage()
    assert "/auth/callback?…" in rec.getMessage()


def test_log_mantem_as_outras_rotas():
    rec = _registro("/api/solicitacoes?escopo=minhas")
    OcultarQuerySensivel().filter(rec)
    assert "/api/solicitacoes?escopo=minhas" in rec.getMessage()
