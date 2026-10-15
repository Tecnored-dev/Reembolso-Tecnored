"""Pedido em nome de outra pessoa (Thais, 13/10/2026).

Qualquer colaborador pode pedir em nome de outro; o dinheiro vai para o
beneficiário e quem aprova é o gestor dele.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from sqlalchemy import select

from app.models import Notificacao
from tests.test_alimentacao import (
    COLAB,
    GESTOR,
    JPG,
    OUTRO_GESTOR,
    THAIS,
    decidir,
    entrar,
)
from tests.test_alimentacao import cenario as cenario  # fixture reaproveitada

BENEF = "beneficiario@tecnored.com.br"
NOVATO = "novato@tecnored.com.br"
HOJE = date.today()


def com_perfil(cliente, email, nome, matricula, papeis=""):
    entrar(cliente, email, papeis, nome)
    r = cliente.put("/api/perfil", json={"matricula": matricula, "centro_custo_id": 2})
    assert r.status_code == 200, r.text


def alimentacao(cliente, quem=COLAB, papeis="", gestor=GESTOR, **benef):
    entrar(cliente, quem, papeis)
    dados = {
        "data_despesa": HOJE.isoformat(),
        "valor": "40,00",
        "descricao": "Almoço na visita",
        "motivo": "Visita técnica",
        "local_refeicao": "outro",
        "empresa_id": "1",
        "centro_custo_id": "1",
        **{f"beneficiario_{k}": str(v) for k, v in benef.items()},
    }
    if gestor:
        dados["gestor_email"] = gestor
    return cliente.post(
        "/api/solicitacoes/alimentacao",
        data=dados,
        files={"arquivo": ("nota.jpg", JPG, "image/jpeg")},
    )


def avisos(db, sol_id):
    return list(db.scalars(select(Notificacao).where(Notificacao.solicitacao_id == sol_id)))


# ---------------------------------------------------------------------------
def test_beneficiario_que_ja_usa_o_sistema(cenario, db):
    com_perfil(cenario, BENEF, "Bia", "5555")
    r = alimentacao(cenario, email=BENEF, matricula="digitada-errada", nome="Outro Nome")
    assert r.status_code == 201, r.text
    sol = r.json()
    # quem recebe é a beneficiária, com a matrícula DELA (o que foi digitado é
    # ignorado); o centro de custo é o escolhido no pedido (Thais, 15/10)
    assert sol["solicitante_email"] == BENEF and sol["solicitante_nome"] == "Bia"
    assert sol["matricula"] == "5555" and sol["centro_custo"] == "3350 - T.I / T.A"
    assert sol["criado_por_email"] == COLAB and sol["criado_por_nome"] == "colab"
    assert sol["gestor_email"] == GESTOR
    # o financeiro recebe o aviso dizendo em nome de quem
    aviso = avisos(db, sol["id"])[0]
    assert "colab (em nome de Bia)" in aviso.corpo


def test_beneficiario_que_nunca_entrou_exige_dados(cenario):
    r = alimentacao(cenario, email=NOVATO)
    assert r.status_code == 400 and "nome da pessoa" in r.json()["detail"]
    r = alimentacao(cenario, email=NOVATO, nome="Novato")
    assert "matrícula da pessoa" in r.json()["detail"]
    r = alimentacao(cenario, email="sem-arroba", nome="X", matricula="1")
    assert "E-mail da pessoa do pedido inválido" in r.json()["detail"]
    # O centro de custo não é mais da pessoa: basta nome e matrícula.
    r = alimentacao(cenario, email=" Novato@Tecnored.com.br ", nome="Novato", matricula="7777")
    assert r.status_code == 201, r.text
    sol = r.json()
    assert sol["solicitante_email"] == NOVATO and sol["solicitante_nome"] == "Novato"
    assert sol["matricula"] == "7777" and sol["centro_custo"] == "3350 - T.I / T.A"


def test_o_proprio_email_e_pedido_normal(cenario):
    r = alimentacao(cenario, email=COLAB, nome="Ignorado")
    assert r.status_code == 201, r.text
    assert r.json()["criado_por_email"] is None and r.json()["solicitante_email"] == COLAB


def test_os_dois_veem_recebem_avisos_e_podem_corrigir(cenario, db):
    com_perfil(cenario, BENEF, "Bia", "5555")
    sol = alimentacao(cenario, email=BENEF).json()
    for quem in (COLAB, BENEF):
        entrar(cenario, quem)
        minhas = cenario.get("/api/solicitacoes", params={"escopo": "minhas"}).json()
        assert [s["id"] for s in minhas] == [sol["id"]]
    # um terceiro não vê
    entrar(cenario, "intruso@tecnored.com.br")
    assert cenario.get(f"/api/solicitacoes/{sol['id']}").status_code == 404

    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro", False, "Nota ilegível")
    devolucao = [n for n in avisos(db, sol["id"]) if "devolvida" in n.assunto.lower()]
    assert set(devolucao[0].para.split(",")) == {COLAB, BENEF}

    for quem in (COLAB, BENEF):
        entrar(cenario, quem)
        assert cenario.get(f"/api/solicitacoes/{sol['id']}").json()["acoes"] == ["reenviar"]
    entrar(cenario, BENEF)
    r = cenario.post(
        f"/api/solicitacoes/{sol['id']}/reenviar",
        data={
            "data_despesa": HOJE.isoformat(),
            "valor": "38,00",
            "descricao": "Almoço na visita",
            "motivo": "Visita técnica",
            "local_refeicao": "outro",
            "empresa_id": "1",
            "gestor_email": GESTOR,
        },
    )
    assert r.status_code == 200, r.text
    # a correção não muda quem recebe
    assert r.json()["solicitante_email"] == BENEF and r.json()["criado_por_email"] == COLAB


def test_beneficiario_gestor_pula_aprovacao(cenario):
    # OUTRO_GESTOR já entrou como gestor (fixture) e completa o perfil
    com_perfil(cenario, OUTRO_GESTOR, "Outro Gestor", "8888", "gestor")
    r = alimentacao(cenario, gestor=None, email=OUTRO_GESTOR)
    assert r.status_code == 201, r.text
    assert r.json()["pula_gestor"] is True and r.json()["gestor_email"] is None


def test_quem_aprova_nao_pode_ser_a_pessoa_nem_quem_criou(cenario):
    com_perfil(cenario, BENEF, "Bia", "5555")
    # gestor criando para a Bia e escolhendo a si mesmo
    r = alimentacao(cenario, quem=GESTOR, papeis="gestor", gestor=GESTOR, email=BENEF)
    assert r.status_code == 400 and "Quem criou o pedido" in r.json()["detail"]
    # colaborador criando para um gestor e escolhendo o próprio gestor como aprovador
    com_perfil(cenario, OUTRO_GESTOR, "Outro Gestor", "8888", "gestor")
    entrar(cenario, COLAB)
    r = alimentacao(cenario, gestor=GESTOR, email=BENEF)
    assert r.status_code == 201, r.text


def test_financeiro_nao_confere_pedido_que_criou(cenario):
    com_perfil(cenario, BENEF, "Bia", "5555")
    r = alimentacao(cenario, quem=THAIS, papeis="financeiro", email=BENEF)
    assert r.status_code == 201, r.text
    sol = r.json()
    assert "conferir" not in sol["acoes"]
    assert decidir(cenario, sol["id"], "conferir", THAIS, "financeiro").status_code == 403


def test_viagem_e_adiantamento_em_nome_de_outra_pessoa(cenario):
    com_perfil(cenario, BENEF, "Bia", "5555")
    entrar(cenario, COLAB)
    ontem = (HOJE - timedelta(days=1)).isoformat()
    r = cenario.post(
        "/api/solicitacoes/viagem",
        data={
            "destino": "Marabá - PA",
            "viagem_inicio": ontem,
            "viagem_fim": ontem,
            "descricao": "Visita",
            "empresa_id": "1",
            "centro_custo_id": "1",
            "gestor_email": GESTOR,
            "beneficiario_email": BENEF,
            "despesas": json.dumps(
                [{"categoria": "taxi_uber", "data_despesa": ontem, "valor": "30", "arquivo": 0}]
            ),
        },
        files=[("arquivos", ("t.jpg", JPG, "image/jpeg"))],
    )
    assert r.status_code == 201, r.text
    assert r.json()["solicitante_email"] == BENEF

    r = cenario.post(
        "/api/solicitacoes/adiantamento",
        json={
            "destino": "São Paulo - SP",
            "viagem_inicio": ontem,
            "viagem_fim": ontem,
            "descricao": "Feira",
            "empresa_id": 1,
            "gestor_email": GESTOR,
            "beneficiario_email": BENEF,
        },
    )
    assert r.status_code == 201, r.text
    sol = r.json()
    assert sol["solicitante_email"] == BENEF and sol["criado_por_email"] == COLAB
    decidir(cenario, sol["id"], "aprovar", GESTOR, "gestor")
    entrar(cenario, THAIS, "financeiro")
    cenario.post(f"/api/solicitacoes/{sol['id']}/pagar", json={"data_pagamento": ontem})
    # quem criou também pode prestar contas
    entrar(cenario, COLAB)
    r = cenario.post(
        f"/api/solicitacoes/{sol['id']}/prestacao",
        data={
            "despesas": json.dumps(
                [{"categoria": "refeicao", "data_despesa": ontem, "valor": "100", "arquivo": 0}]
            )
        },
        files=[("arquivos", ("n.jpg", JPG, "image/jpeg"))],
    )
    assert r.status_code == 200, r.text


def test_busca_de_colegas(cenario):
    com_perfil(cenario, BENEF, "Bia Souza", "5555")
    entrar(cenario, COLAB)
    assert cenario.get("/api/usuarios", params={"busca": "b"}).json() == []  # mínimo 2 letras
    achados = cenario.get("/api/usuarios", params={"busca": "souza"}).json()
    assert achados == [
        {"email": BENEF, "nome": "Bia Souza", "perfil_completo": True, "eh_gestor": False}
    ]
    gestores = cenario.get("/api/usuarios", params={"busca": "gestor"}).json()
    assert {g["email"] for g in gestores} == {GESTOR, OUTRO_GESTOR}
    assert all(g["eh_gestor"] for g in gestores)
    # o próprio usuário não aparece
    assert cenario.get("/api/usuarios", params={"busca": "colab"}).json() == []
