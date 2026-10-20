"""Painel de teste ("Ver como"): só admin, só ligado, e sem misturar teste com real."""

from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import Notificacao, Solicitacao
from app.services import painel_teste as painel
from tests.test_alimentacao import cenario as cenario
from tests.test_alimentacao import entrar

ADMIN = "rizzo@tecnored.com.br"
COLAB_TESTE, GESTOR_TESTE, FIN_TESTE = (u.email for u in painel.USUARIOS_TESTE)


@pytest.fixture
def ligado(cenario, settings):
    """Admin logado e painel ligado (como em hml)."""
    from app.main import app

    ligada = replace(settings, painel_teste_enabled=True, painel_teste_admins=ADMIN)
    app.dependency_overrides[get_settings] = lambda: ligada
    entrar(cenario, ADMIN, "", "Rizzo")
    return cenario


def estado(cliente):
    r = cliente.get("/api/teste/estado")
    assert r.status_code == 200, r.text
    return r.json()


def ver_como(cliente, email):
    r = cliente.post("/api/teste/ver-como", json={"email": email})
    assert r.status_code == 200, r.text


def test_desligado_nao_existe(cenario):
    entrar(cenario, ADMIN, "", "Rizzo")
    assert estado(cenario) == {"ativo": False, "admin": False, "vendo_como": None, "usuarios": []}
    for rota in ("ver-como", "voltar", "demo", "limpar"):
        assert cenario.post(f"/api/teste/{rota}", json={"email": COLAB_TESTE}).status_code == 404


def test_main_nunca_liga():
    from app.config import Settings

    cfg = Settings(app_env="main", db_url="sqlite://", painel_teste_enabled=True)
    with pytest.raises(RuntimeError, match="PAINEL_TESTE_ENABLED"):
        cfg.validar()


def test_so_admin_usa(ligado):
    entrar(ligado, "joao@tecnored.com.br", "", "João")  # login de dev: local
    # (a sessão já existe; só a config do painel muda)
    est = estado(ligado)
    assert est["ativo"] is True and est["admin"] is False and est["usuarios"] == []
    assert ligado.post("/api/teste/ver-como", json={"email": COLAB_TESTE}).status_code == 403
    assert ligado.post("/api/teste/demo").status_code == 403
    assert ligado.post("/api/teste/limpar").status_code == 403


def test_funciona_em_hml(cenario, settings):
    from app.main import app

    entrar(cenario, ADMIN, "", "Rizzo")  # o login de dev só existe em local
    hml = replace(
        settings,
        app_env="hml",
        dev_login_enabled=False,
        painel_teste_enabled=True,
        painel_teste_admins=ADMIN,
    )
    app.dependency_overrides[get_settings] = lambda: hml
    cenario.base_url = "https://testserver"  # em hml os cookies são `secure`
    assert estado(cenario)["admin"] is True
    ver_como(cenario, COLAB_TESTE)
    assert cenario.get("/api/session").json()["email"] == COLAB_TESTE
    assert cenario.post("/api/teste/voltar").status_code == 200
    assert cenario.get("/api/session").json()["email"] == ADMIN


def test_admin_por_grupo_do_azure(cenario, settings):
    from app.main import app

    entrar(cenario, "ana@tecnored.com.br", "admin", "Ana")
    app.dependency_overrides[get_settings] = lambda: replace(
        settings, app_env="hml", painel_teste_enabled=True
    )
    assert estado(cenario)["admin"] is True


def test_ver_como_troca_e_volta(ligado):
    est = estado(ligado)
    assert est["admin"] and est["vendo_como"] is None
    assert [u["chave"] for u in est["usuarios"]] == ["colaborador", "gestor", "financeiro"]

    ver_como(ligado, FIN_TESTE)
    sessao = ligado.get("/api/session").json()
    assert sessao["email"] == FIN_TESTE and "financeiro" in sessao["papeis"]
    est = estado(ligado)
    assert est["admin"] and est["vendo_como"]["nome"] == "Financeiro Teste"

    # Trocar de novo mantém a sessão original do admin.
    ver_como(ligado, GESTOR_TESTE)
    assert ligado.get("/api/session").json()["email"] == GESTOR_TESTE

    assert ligado.post("/api/teste/voltar").status_code == 200
    assert ligado.get("/api/session").json()["email"] == ADMIN
    assert estado(ligado)["vendo_como"] is None
    assert ligado.post("/api/teste/voltar").status_code == 400  # já voltou


def test_so_usuarios_de_teste(ligado):
    r = ligado.post("/api/teste/ver-como", json={"email": "thais@tecnored.com.br"})
    assert r.status_code == 400
    assert ligado.get("/api/session").json()["email"] == ADMIN


def test_usuario_de_teste_nao_e_admin_nem_sobe_de_nivel(ligado):
    ver_como(ligado, COLAB_TESTE)
    assert ligado.post("/api/teste/demo").status_code == 201  # o admin real segue valendo
    # ...mas um usuário comum não consegue usar o cookie do admin: sem o cookie, 403.
    ligado.cookies.delete(painel.COOKIE_ADMIN)
    assert estado(ligado)["admin"] is False
    assert ligado.post("/api/teste/ver-como", json={"email": FIN_TESTE}).status_code == 403


def test_usuarios_de_teste_entram_ja_com_perfil(ligado):
    ver_como(ligado, COLAB_TESTE)
    perfil = ligado.get("/api/perfil").json()
    assert perfil["matricula"] == painel.MATRICULA_TESTE


def test_demo_cria_pedidos_em_varias_etapas(ligado, db):
    r = ligado.post("/api/teste/demo")
    assert r.status_code == 201, r.text
    assert len(r.json()["criados"]) == 9
    status = {s.status for s in db.scalars(select(Solicitacao)).all()}
    assert {
        "em_conferencia",
        "devolvido",
        "aguardando_gestor",
        "aguardando_pagamento",
        "aguardando_prestacao",
        "pago",
        "recusado",
    } <= status
    tipos = {s.tipo for s in db.scalars(select(Solicitacao)).all()}
    assert tipos == {"alimentacao", "diversas", "viagem", "adiantamento"}
    assert all(painel.eh_teste(s.solicitante_email) for s in db.scalars(select(Solicitacao)))

    ver_como(ligado, GESTOR_TESTE)
    aprovacoes = ligado.get("/api/solicitacoes", params={"escopo": "aprovacao"}).json()
    assert len(aprovacoes) == 2  # despesas diversas conferidas + adiantamento


def test_teste_e_real_nao_se_misturam(ligado, db):
    ligado.post("/api/teste/demo")
    # Financeiro real (Thais) não vê nada de teste nas filas.
    entrar(ligado, "thais@tecnored.com.br", "financeiro", "Thais")
    for escopo in ("conferencia", "pagamento", "todas"):
        assert ligado.get("/api/solicitacoes", params={"escopo": escopo}).json() == []
    # Financeiro de teste vê.
    entrar(ligado, ADMIN, "", "Rizzo")
    ver_como(ligado, FIN_TESTE)
    assert len(ligado.get("/api/solicitacoes", params={"escopo": "conferencia"}).json()) == 2
    # Avisos de pedido de teste só vão para gente de teste.
    for aviso in db.scalars(select(Notificacao)).all():
        assert all(painel.eh_teste(e) for e in aviso.para.split(","))


def test_gestores_listados_para_cada_lado(ligado):
    ver_como(ligado, COLAB_TESTE)
    nomes = [g["nome"] for g in ligado.get("/api/gestores").json()]
    assert nomes == ["Gestor Teste"]
    ligado.post("/api/teste/voltar")
    entrar(ligado, "joao@tecnored.com.br", "", "João")
    assert "Gestor Teste" not in [g["nome"] for g in ligado.get("/api/gestores").json()]


def test_limpar_apaga_so_pedido_de_teste(ligado, db):
    ligado.post("/api/teste/demo")
    real = Solicitacao(
        tipo="alimentacao",
        status="em_conferencia",
        solicitante_email="real@tecnored.com.br",
        solicitante_nome="Real",
        matricula="1",
        empresa="TECNORED",
        descricao="x",
        valor_total=10,
        enviado_em=painel.agora_utc(),
        ultima_movimentacao_em=painel.agora_utc(),
    )
    db.add(real)
    db.commit()
    guardadas = list(ligado.storage.raiz.rglob("*.png"))  # type: ignore[attr-defined]
    assert guardadas, "a demonstração grava as notas"

    r = ligado.post("/api/teste/limpar")
    assert r.status_code == 200 and r.json()["apagados"] == 9
    restantes = db.scalars(select(Solicitacao)).all()
    assert [s.solicitante_email for s in restantes] == ["real@tecnored.com.br"]
    assert not list(ligado.storage.raiz.rglob("*.png"))  # type: ignore[attr-defined]
    assert db.scalars(select(Notificacao)).all() == []


def test_logout_durante_ver_como_nao_deixa_admin_para_o_proximo(ligado):
    """Sair enquanto vê como outro não pode deixar o poder de admin no navegador."""
    ver_como(ligado, COLAB_TESTE)
    ligado.get("/logout", follow_redirects=False)
    entrar(ligado, "outro@tecnored.com.br", "", "Outro")
    assert estado(ligado)["admin"] is False
    assert ligado.post("/api/teste/demo").status_code == 403
    assert ligado.post("/api/teste/ver-como", json={"email": FIN_TESTE}).status_code == 403
    assert ligado.post("/api/teste/voltar").status_code == 400


def test_cookie_antigo_do_admin_nao_derruba_a_sessao_real(ligado):
    """Cookie guardado velho (sessão de teste já encerrada) não pode ser reaproveitado."""
    ver_como(ligado, COLAB_TESTE)
    cookie_velho = ligado.cookies.get(painel.COOKIE_ADMIN)
    ligado.get("/logout", follow_redirects=False)
    entrar(ligado, ADMIN, "", "Rizzo")
    ligado.cookies.set(painel.COOKIE_ADMIN, cookie_velho, domain="testserver")
    ver_como(ligado, FIN_TESTE)
    assert ligado.post("/api/teste/voltar").status_code == 200
    assert ligado.get("/api/session").json()["email"] == ADMIN


def test_notas_da_demonstracao_tem_cupom_legivel():
    """A foto da nota na demonstração é um cupom fictício, não um pixel em branco."""
    from decimal import Decimal

    for valor in ("38.50", "52.00", "89.90", "25.00", "31.00", "240.00"):
        arq = painel._arquivo_nota(Decimal(valor))
        assert arq.tipo == "image/png" and len(arq.conteudo) > 5000, valor
    # valor sem imagem própria cai no PNG de reserva, sem quebrar a demonstração
    assert painel._arquivo_nota(Decimal("1.23")).tipo == "image/png"
