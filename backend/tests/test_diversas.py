"""Despesas diversas (Nirlene, 13/10/2026): tudo que não é alimentação, viagem
nem adiantamento. Desde 15/10 faz parte do "Reembolso de despesas - Prestação
de Contas": várias notas e sem o limite de refeição. Desde 29/10 a categoria da
nota é escolhida aqui (a alimentação só aceita refeição e almoço em Pinda)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.models import Notificacao
from tests.test_alimentacao import (
    COLAB,
    GESTOR,
    JPG,
    PDF,
    THAIS,
    decidir,
    entrar,
    nota_despesa,
    reenviar,
)
from tests.test_alimentacao import cenario as cenario  # fixture reaproveitada
from tests.test_alimentacao import enviar as enviar_alimentacao

HOJE = date.today().isoformat()


def enviar(cliente, valor="189,90", descricao="Carregador de notebook", **extra):
    extra.setdefault("motivo", "Trabalho externo")
    extra.setdefault("categoria", "hospedagem")
    return enviar_alimentacao(
        cliente,
        valor=valor,
        descricao=descricao,
        rota="diversas",
        arquivo=("nota.pdf", PDF, "application/pdf"),
        **extra,
    )


def test_fluxo_completo(cenario, db):
    entrar(cenario, COLAB)
    r = enviar(cenario)
    assert r.status_code == 201, r.text
    sol = r.json()
    assert sol["tipo"] == "diversas" and sol["tipo_rotulo"] == "Despesas diversas"
    assert sol["status"] == "em_conferencia" and sol["valor_total"] == "189.90"
    assert sol["despesas"][0]["categoria"] == "hospedagem"
    assert sol["despesas"][0]["categoria_rotulo"] == "Hospedagem"
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
    assert "por dia" in enviar_alimentacao(cenario, valor="900,00").json()["alerta_limite"]


def test_validacoes_iguais_a_alimentacao(cenario):
    entrar(cenario, COLAB)
    assert "Descreva a despesa" in enviar(cenario, descricao="  ").json()["detail"]
    r = enviar_alimentacao(
        cenario, rota="diversas", arquivo=None, motivo="Outros", categoria="hospedagem"
    )
    assert "anexe a foto ou o PDF" in r.json()["detail"]
    assert "Gestor não encontrado" in enviar(cenario, gestor_email="x@y.com").json()["detail"]


def test_correcao_pela_mesma_rota_da_alimentacao(cenario):
    entrar(cenario, COLAB)
    sol = enviar(cenario).json()
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro", False, "Valor errado")
    entrar(cenario, COLAB)
    nota = nota_despesa("179,90", None, "hospedagem", 0, id=sol["despesas"][0]["id"])
    r = reenviar(
        cenario,
        sol,
        [nota],
        [("arquivos", ("nova.jpg", JPG, "image/jpeg"))],
        descricao="Carregador de notebook",
        motivo="Trabalho externo",
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["tipo"] == "diversas" and corpo["valor_total"] == "179.90"
    assert corpo["status"] == "em_conferencia" and corpo["alerta_limite"] is None
    assert corpo["despesas"][0]["categoria"] == "hospedagem"


def test_em_nome_de_outra_pessoa(cenario):
    entrar(cenario, COLAB)
    r = enviar(
        cenario,
        beneficiario_email="ti@tecnored.com.br",
        beneficiario_nome="Pessoa da TI",
        beneficiario_matricula="4242",
    )
    assert r.status_code == 201, r.text
    assert r.json()["solicitante_nome"] == "Pessoa da TI"
    assert r.json()["criado_por_email"] == COLAB


def test_diversas_tem_motivo_mas_nao_local(cenario):
    entrar(cenario, COLAB)
    assert "Escolha o motivo" in enviar(cenario, motivo="").json()["detail"]
    sol = enviar(cenario, motivo="Despesas correio").json()
    assert sol["motivo"] == "Despesas correio" and sol["local_refeicao"] is None


def test_categoria_obrigatoria_e_so_as_de_diversas(cenario):
    entrar(cenario, COLAB)
    # refeição é da alimentação; "diversos" era o nome antigo
    for categoria in (
        "",
        "refeicao",
        "refeicao_internacional",
        "almoco_pinda",
        "churrasco",
        "diversos",
    ):
        r = enviar(cenario, categoria=categoria)
        assert r.status_code == 400 and "categoria inválida" in r.json()["detail"], categoria
    for categoria in ("taxi_uber", "combustivel", "quilometragem_nao_existe"):
        assert enviar(cenario, categoria=categoria).status_code == (
            201 if categoria != "quilometragem_nao_existe" else 400
        )


def test_cadastros_separam_as_categorias_por_tipo(cenario):
    entrar(cenario, COLAB)
    dados = cenario.get("/api/cadastros").json()
    alimentacao = [c["id"] for c in dados["categorias_alimentacao"]]
    diversas = [c["id"] for c in dados["categorias_diversas"]]
    assert alimentacao == ["refeicao", "refeicao_internacional", "almoco_pinda"]
    assert not set(alimentacao) & set(diversas)
    assert {"taxi_uber", "quilometragem", "despesas_diversas"} <= set(diversas)
    assert len(alimentacao) + len(diversas) == len(dados["categorias_viagem"]) == 16


def test_pedido_antigo_com_categoria_antiga_ainda_pode_ser_corrigido(cenario, db):
    from app.models import Despesa

    entrar(cenario, COLAB)
    sol = enviar(cenario).json()
    despesa = db.get(Despesa, sol["despesas"][0]["id"])
    despesa.categoria = "diversos"  # como eram gravadas antes de 29/10
    db.commit()
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro", False, "Valor errado")
    entrar(cenario, COLAB)
    antiga = nota_despesa("150,00", None, "diversos", None, id=despesa.id)
    r = reenviar(cenario, sol, [antiga], descricao="Carregador", motivo="Trabalho externo")
    assert r.status_code == 200, r.text
    assert r.json()["despesas"][0]["categoria_rotulo"] == "Despesas diversas"
