"""Regras da Thais de 15/10/2026: perfil só com matrícula, centro de custo no
pedido (sugerindo o último usado), adiantamento sem centro de custo e nomes
novos dos status. A recusa do gestor está em test_alimentacao e test_adiantamento."""

from __future__ import annotations

from tests.test_adiantamento import criar_adiantamento
from tests.test_alimentacao import (
    COLAB,
    GESTOR,
    THAIS,
    criar,
    decidir,
    entrar,
    enviar,
    nota_despesa,
    reenviar,
)
from tests.test_alimentacao import cenario as cenario  # fixture reaproveitada


def test_perfil_so_com_matricula(cliente):
    entrar(cliente, GESTOR, "gestor")
    entrar(cliente, COLAB)
    assert cliente.get("/api/perfil").json()["completo"] is False
    r = cliente.put("/api/perfil", json={"matricula": "4321"})
    assert r.status_code == 200, r.text
    assert r.json()["completo"] is True and r.json()["centro_custo"] is None
    # Já dá para pedir, escolhendo o centro de custo no pedido.
    r = enviar(cliente)
    assert r.status_code == 201, r.text
    assert r.json()["matricula"] == "4321" and r.json()["centro_custo"] == "3350 - T.I / T.A"


def test_centro_de_custo_obrigatorio_e_valido_no_pedido(cenario):
    entrar(cenario, COLAB)
    for invalido in ("", "999", "abc"):
        r = enviar(cenario, centro_custo_id=invalido)
        assert r.status_code == 400 and "entro de custo" in r.json()["detail"], invalido


def test_ultimo_centro_de_custo_usado_vira_sugestao(cenario):
    entrar(cenario, COLAB)
    assert enviar(cenario, centro_custo_id="2").status_code == 201
    perfil = cenario.get("/api/perfil").json()
    assert perfil["centro_custo"] == {"id": 2, "rotulo": "4110 - CONTROLADORIA"}
    assert enviar(cenario, centro_custo_id="1").status_code == 201
    assert cenario.get("/api/perfil").json()["centro_custo"]["id"] == 1


def test_correcao_pode_trocar_o_centro_de_custo(cenario):
    sol = criar(cenario)
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro", False, "Centro de custo errado")
    entrar(cenario, COLAB)
    notas = [nota_despesa(arquivo=None, id=sol["despesas"][0]["id"])]
    # Sem centro de custo: mantém o do pedido.
    r = reenviar(cenario, sol, notas, centro_custo_id="")
    assert r.status_code == 200 and r.json()["centro_custo"] == "3350 - T.I / T.A"
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro", False, "De novo")
    entrar(cenario, COLAB)
    r = reenviar(cenario, sol, notas, centro_custo_id="2")
    assert r.status_code == 200 and r.json()["centro_custo"] == "4110 - CONTROLADORIA"


def test_adiantamento_nao_tem_centro_de_custo(cenario):
    sol = criar_adiantamento(cenario)
    assert sol["centro_custo"] is None


def test_salvar_a_data_do_pagamento_finaliza(cenario):
    sol = criar(cenario)
    assert sol["status_rotulo"] == "Pendente de conferência"
    r = decidir(cenario, sol["id"], "conferir", THAIS, "financeiro")
    assert r.json()["status_rotulo"] == "Pendente de aprovação"
    r = decidir(cenario, sol["id"], "aprovar", GESTOR, "gestor")
    assert r.json()["status_rotulo"] == "Aguardando pagamento"
    entrar(cenario, THAIS, "financeiro")
    assert cenario.get(f"/api/solicitacoes/{sol['id']}").json()["acoes"] == ["pagar"]
    r = cenario.post(f"/api/solicitacoes/{sol['id']}/pagar", json={"data_pagamento": "2026-10-20"})
    pago = r.json()
    assert pago["status"] == "pago" and pago["status_rotulo"] == "Finalizado - Pago"
    assert pago["data_pagamento"] == "2026-10-20" and pago["acoes"] == []
