from __future__ import annotations

from datetime import timedelta

import pytest

from app.auth import sessoes
from app.auth.papeis import papeis_publicos, resolver_papeis
from app.config import Settings
from app.models.sessao import Sessao


def test_papeis_por_grupo(settings):
    assert resolver_papeis(["x", "g-gestor"], settings) == ["gestor"]
    assert resolver_papeis(["g-fin", "g-admin"], settings) == ["financeiro", "admin"]
    assert resolver_papeis([], settings) == []


def test_sem_grupo_e_colaborador():
    assert papeis_publicos([]) == ["colaborador"]
    assert papeis_publicos(["admin", "gestor"]) == ["colaborador", "gestor", "admin"]


def test_grupo_nao_configurado_nao_da_papel():
    s = Settings(db_url="x", grupo_gestor="")
    assert resolver_papeis([""], s) == []


def test_sessao_persistida_guarda_so_hash(db):
    token = sessoes.criar_sessao(
        db,
        email="Ana@Tecnored.com.br",
        nome="Ana",
        grupos=["g"],
        papeis=["gestor"],
        via="microsoft",
    )
    linha = db.query(Sessao).one()
    assert linha.token_hash != token and len(linha.token_hash) == 64
    u = sessoes.obter_usuario(db, token)
    assert u.email == "ana@tecnored.com.br" and u.tem("gestor")


def test_sessao_expirada(db):
    token = sessoes.criar_sessao(db, email="a@x", nome="A", grupos=[], papeis=[], via="dev")
    linha = db.query(Sessao).one()
    linha.expira_em = sessoes.agora_utc() - timedelta(minutes=1)
    db.commit()
    assert sessoes.obter_usuario(db, token) is None


def test_token_invalido(db):
    assert sessoes.obter_usuario(db, None) is None
    assert sessoes.obter_usuario(db, "qualquer") is None


def test_dev_login_e_sessao(cliente):
    assert cliente.get("/api/session").status_code == 401
    r = cliente.get("/dev/login?email=thais@tecnored.com.br&nome=Thais&papeis=financeiro,xpto")
    assert r.status_code == 302 and r.headers["location"] == "http://front/inicio"
    cliente.cookies.set(sessoes.COOKIE, r.cookies[sessoes.COOKIE])
    s = cliente.get("/api/session").json()
    assert s["papeis"] == ["colaborador", "financeiro"]
    assert s["login_method"] == "dev"


def test_logout_apaga_sessao(cliente, db):
    r = cliente.get("/dev/login")
    cliente.cookies.set(sessoes.COOKIE, r.cookies[sessoes.COOKIE])
    r = cliente.get("/logout")
    assert r.status_code == 302 and r.headers["location"] == "http://front"
    assert db.query(Sessao).count() == 0


def test_dev_login_desligado_fora_do_local(cliente, settings):
    from app.config import get_settings
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: Settings(
        app_env="hml", db_url="x", dev_login_enabled=True
    )
    assert cliente.get("/dev/login").status_code == 404


def test_api_nao_sobe_com_dev_login_em_hml():
    with pytest.raises(RuntimeError):
        Settings(app_env="hml", db_url="x", dev_login_enabled=True).validar()


def test_login_sem_azure_avisa_o_front(cliente):
    r = cliente.get("/login")
    assert r.status_code == 307
    assert "auth_error=azure_nao_configurado" in r.headers["location"]


def test_sso_cloudflare_cria_sessao(cliente, settings, monkeypatch, db):
    async def fake(request, s):
        return {"email": "cf@tecnored.com.br", "name": "CF", "groups": [{"id": "g-gestor"}]}

    monkeypatch.setattr("app.auth.deps.identidade_cloudflare", fake)
    r = cliente.get("/api/session")
    assert r.status_code == 200
    assert r.json()["papeis"] == ["colaborador", "gestor"]
    assert r.json()["login_method"] == "cloudflare"
    assert sessoes.COOKIE in r.cookies
