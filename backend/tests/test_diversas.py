"""Despesas diversas (Nirlene, 13/10/2026): tudo que não é alimentação, viagem
nem adiantamento. Mesmo fluxo e formulário da alimentação, sem o limite de
refeição."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.models import Notificacao
from tests.test_alimentacao import COLAB, GESTOR, JPG, PDF, THAIS, decidir, entrar
from tests.test_alimentacao import cenario as cenario  # fixture reaproveitada
from tests.test_alimentacao import enviar as enviar_alimentacao

HOJE = date.today().isoformat()


def enviar(cliente, valor="189,90", descricao="Carregador de notebook", **extra):
    dados = {
        "data_despesa": HOJE,
        "valor": valor,
        "descricao": descricao,
        "motivo": "Trabalho externo",
        "empresa_id": "1",
        "gestor_email": GESTOR,
        **extra,
    }
    return cliente.post(
        "/api/solicitacoes/diversas",
        data=dados,
        files={"arquivo": ("nota.pdf", PDF, "application/pdf")},
    )


def test_fluxo_completo(cenario, db):
    entrar(cenario, COLAB)
    r = enviar(cenario)
    assert r.status_code == 201, r.text
    sol = r.json()
    assert sol["tipo"] == "diversas" and sol["tipo_rotulo"] == "Despesas diversas"
    assert sol["status"] == "em_conferencia" and sol["valor_total"] == "189.90"
    assert sol["despesas"][0]["categoria"] == "diversos"
    assert sol["despesas"][0]["categoria_rotulo"] == "Despesas diversas"
    aviso = db.scalar(select(Notificacao).where(Notificacao.solicitacao_id == sol["id"]))
    assert "reembolso de despesas diversas" in aviso.corpo

    assert decidir(cenario, sol["id"], "conferir", THAIS, "financeiro").json()["status"] == (
        "aguardando_gestor"
    )
    assert decidir(cenario, sol["id"], "aprovar", GESTOR, "gestor").json()["status"] == (
        "aguardando_pagamento"
    )
    entrar(cenario, THAIS, "financeiro")
    r = cenario.post(f"/api/solicitacoes/{sol['id']}/pagar", json={"data_pagamento": HOJE})
    assert r.json()["status"] == "pago"


def test_sem_limite_de_refeicao(cenario):
    entrar(cenario, COLAB)
    sol = enviar(cenario, valor="900,00").json()
    assert sol["alerta_limite"] is None
    # a alimentação continua com o alerta
    assert "limite diário" in enviar_alimentacao(cenario, valor="900,00").json()["alerta_limite"]


def test_validacoes_iguais_a_alimentacao(cenario):
    entrar(cenario, COLAB)
    assert "Descreva a despesa" in enviar(cenario, descricao="  ").json()["detail"]
    r = cenario.post(
        "/api/solicitacoes/diversas",
        data={
            "data_despesa": HOJE,
            "valor": "10",
            "descricao": "x",
            "motivo": "Outros",
            "empresa_id": "1",
            "gestor_email": GESTOR,
        },
    )
    assert "Anexe a foto ou o PDF" in r.json()["detail"]
    assert "Gestor não encontrado" in enviar(cenario, gestor_email="x@y.com").json()["detail"]


def test_correcao_pela_mesma_rota_da_alimentacao(cenario):
    entrar(cenario, COLAB)
    sol = enviar(cenario).json()
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro", False, "Valor errado")
    entrar(cenario, COLAB)
    r = cenario.post(
        f"/api/solicitacoes/{sol['id']}/reenviar",
        data={
            "data_despesa": HOJE,
            "valor": "179,90",
            "descricao": "Carregador de notebook",
            "motivo": "Trabalho externo",
            "empresa_id": "1",
            "gestor_email": GESTOR,
        },
        files={"arquivo": ("nova.jpg", JPG, "image/jpeg")},
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["tipo"] == "diversas" and corpo["valor_total"] == "179.90"
    assert corpo["status"] == "em_conferencia" and corpo["alerta_limite"] is None
    assert corpo["despesas"][0]["categoria"] == "diversos"


def test_em_nome_de_outra_pessoa(cenario):
    entrar(cenario, COLAB)
    r = enviar(
        cenario,
        beneficiario_email="ti@tecnored.com.br",
        beneficiario_nome="Pessoa da TI",
        beneficiario_matricula="4242",
        beneficiario_centro_custo_id="1",
    )
    assert r.status_code == 201, r.text
    assert r.json()["solicitante_nome"] == "Pessoa da TI"
    assert r.json()["criado_por_email"] == COLAB


def test_diversas_tem_motivo_mas_nao_local(cenario):
    entrar(cenario, COLAB)
    assert "Escolha o motivo" in enviar(cenario, motivo="").json()["detail"]
    sol = enviar(cenario, motivo="Despesas correio").json()
    assert sol["motivo"] == "Despesas correio" and sol["local_refeicao"] is None
