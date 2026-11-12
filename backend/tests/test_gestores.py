"""Lista de gestores: cópia do grupo do Azure atualizada no login (permissão delegada)."""

from __future__ import annotations

import dataclasses
from datetime import datetime

import pytest

from app.models import GestorGrupo
from app.services import gestores
from app.services.gestores import Gestor

AGORA = datetime(2026, 10, 7, 12, 0)


@pytest.fixture(autouse=True)
def _limpa_cache():
    gestores._cache.clear()
    yield
    gestores._cache.clear()


def test_sincroniza_e_lista_da_copia(db, settings, monkeypatch):
    monkeypatch.setattr(
        gestores,
        "buscar_membros",
        lambda token, grupo: [Gestor("nirlene@t.com", "Nirlene"), Gestor("ana@t.com", "Ana")],
    )
    assert gestores.sincronizar_no_login(db, settings, "token", AGORA) is True
    db.commit()
    assert [g.nome for g in gestores.listar(db, settings)] == ["Ana", "Nirlene"]


def test_quem_sai_do_grupo_some_no_proximo_login(db, settings, monkeypatch):
    monkeypatch.setattr(
        gestores, "buscar_membros", lambda t, g: [Gestor("a@t.com", "A"), Gestor("b@t.com", "B")]
    )
    gestores.sincronizar_no_login(db, settings, "t", AGORA)
    monkeypatch.setattr(gestores, "buscar_membros", lambda t, g: [Gestor("b@t.com", "B")])
    gestores.sincronizar_no_login(db, settings, "t", AGORA)
    db.commit()
    assert [g.email for g in gestores.listar(db, settings)] == ["b@t.com"]


def test_erro_no_graph_mantem_a_copia_anterior(db, settings, monkeypatch):
    monkeypatch.setattr(gestores, "buscar_membros", lambda t, g: [Gestor("a@t.com", "A")])
    gestores.sincronizar_no_login(db, settings, "t", AGORA)
    db.commit()

    def falha(t, g):
        raise RuntimeError("403 Forbidden")

    monkeypatch.setattr(gestores, "buscar_membros", falha)
    assert gestores.sincronizar_no_login(db, settings, "t", AGORA) is False
    db.commit()
    assert [g.email for g in gestores.listar(db, settings)] == ["a@t.com"]


def test_sem_grupo_configurado_nao_consulta(db, settings, monkeypatch):
    sem_grupo = dataclasses.replace(settings, grupo_gestor="")

    def nao_deveria(t, g):
        raise AssertionError("não deveria chamar o Graph")

    monkeypatch.setattr(gestores, "buscar_membros", nao_deveria)
    assert gestores.sincronizar_no_login(db, sem_grupo, "t", AGORA) is False


def test_sem_copia_usa_quem_ja_entrou_como_gestor(cliente, db):
    cliente.get("/dev/login", params={"email": "g@t.com", "nome": "G", "papeis": "gestor"})
    cliente.get("/dev/login", params={"email": "colab@t.com", "nome": "C"})
    assert db.query(GestorGrupo).count() == 0
    assert [g["email"] for g in cliente.get("/api/gestores").json()] == ["g@t.com"]


def test_login_microsoft_atualiza_a_lista(cliente, db, settings, monkeypatch):
    """O callback do Azure usa o token de quem loga para ler o grupo de gestores."""
    from app.api.routes import auth
    from app.config import get_settings
    from app.main import app

    com_azure = dataclasses.replace(
        settings, azure_client_id="id", azure_client_secret="s", azure_tenant_id="t"
    )
    app.dependency_overrides[get_settings] = lambda: com_azure

    class MsalFalso:
        def acquire_token_by_authorization_code(self, **_):
            return {
                "access_token": "token-do-usuario",
                "id_token_claims": {"preferred_username": "colab@t.com", "name": "Colab"},
            }

    class RespostaFalsa:
        status_code = 200

        def json(self):
            return {"value": []}

    class ClienteFalso:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return RespostaFalsa()

    tokens = []
    monkeypatch.setattr(auth, "_msal", lambda s: MsalFalso())
    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **k: ClienteFalso())
    monkeypatch.setattr(
        gestores,
        "buscar_membros",
        lambda token, grupo: tokens.append((token, grupo)) or [Gestor("nirlene@t.com", "Nirlene")],
    )

    cliente.cookies.set("oauth_state", "st", path="/auth/callback")
    r = cliente.get("/auth/callback", params={"code": "abc", "state": "st"})
    assert r.status_code == 302
    assert tokens == [("token-do-usuario", "g-gestor")]
    assert [g["email"] for g in cliente.get("/api/gestores").json()] == ["nirlene@t.com"]


def test_membros_sem_email_nao_apagam_a_copia(db, settings, monkeypatch):
    """Sem permissão para ler perfis, o Graph manda só o id: não pode zerar a lista."""
    monkeypatch.setattr(gestores, "buscar_membros", lambda t, g: [Gestor("a@t.com", "A")])
    gestores.sincronizar_no_login(db, settings, "t", AGORA)
    db.commit()

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"value": [{"id": "1"}, {"id": "2"}]}

    class Cli:
        def __init__(self, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            return Resp()

    monkeypatch.undo()
    monkeypatch.setattr(gestores.httpx, "Client", Cli)
    with pytest.raises(RuntimeError, match=r"User\.ReadBasic\.All"):
        gestores.buscar_membros("t", "g")
    assert gestores.sincronizar_no_login(db, settings, "t", AGORA) is False
    db.commit()
    assert [g.email for g in gestores.listar(db, settings)] == ["a@t.com"]
