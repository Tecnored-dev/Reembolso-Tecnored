"""Diária de Viagem (Thais, 15/10): linhas de valor integral ou parcial, sem notas.

Os helpers `nota`, `TRES_NOTAS` e `TRES_ARQUIVOS` ficam aqui porque os testes de
adiantamento (prestação de contas) e de terceiros também usam notas."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.models import Despesa, Solicitacao
from tests.test_alimentacao import (
    COLAB,
    GESTOR,
    JPG,
    PDF,
    THAIS,
    decidir,
    entrar,
)
from tests.test_alimentacao import cenario as cenario  # fixture reaproveitada
from tests.test_alimentacao import enviar as enviar_alimentacao

HOJE = date.today()
ONTEM = HOJE - timedelta(days=1)
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 200


def nota(categoria="refeicao", valor="50,00", dia=ONTEM, descricao="", arquivo=None, id=None):
    item = {
        "categoria": categoria,
        "data_despesa": dia.isoformat(),
        "valor": valor,
        "descricao": descricao,
    }
    if arquivo is not None:
        item["arquivo"] = arquivo
    if id is not None:
        item["id"] = id
    return item


VIAGEM_INICIO = HOJE - timedelta(days=3)  # ida e volta (até ontem) = 3 dias


def integral(quantidade=1) -> dict:
    return {"tipo": "integral", "quantidade": quantidade}


def parcial(quantidade=1, valor="80,00") -> dict:
    return {"tipo": "parcial", "quantidade": quantidade, "valor": valor}


def pedido_diaria(linhas=None, gestor=GESTOR, **extra) -> dict:
    dados = {
        "destino": "Marabá - PA",
        "viagem_inicio": VIAGEM_INICIO.isoformat(),
        "viagem_fim": ONTEM.isoformat(),
        "descricao": "Visita técnica à planta",
        "empresa_id": 1,
        "centro_custo_id": "1",
        "internacional": False,
        "linhas": [integral(2), parcial(1)] if linhas is None else linhas,
        **extra,
    }
    if gestor:
        dados.setdefault("gestor_email", gestor)
    return dados


TRES_NOTAS = [
    nota("refeicao", "45,90", arquivo=0),
    nota("hospedagem", "320,00", arquivo=1),
    nota("taxi_uber", "88,10", arquivo=2, descricao="Táxi aeroporto"),
]
TRES_ARQUIVOS = [
    ("almoco.jpg", JPG, "image/jpeg"),
    ("hotel.pdf", PDF, "application/pdf"),
    ("taxi.png", PNG, "image/png"),
]


def criar_viagem(cliente, linhas=None, **extra) -> dict:
    entrar(cliente, COLAB, "", "Colab")
    r = cliente.post("/api/solicitacoes/viagem", json=pedido_diaria(linhas, **extra))
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
def test_fluxo_completo_com_linhas_integral_e_parcial(cenario):
    sol = criar_viagem(cenario)
    assert sol["tipo"] == "viagem" and sol["tipo_rotulo"] == "Diária de Viagem"
    assert sol["status"] == "em_conferencia" and sol["viagem_internacional"] is False
    assert sol["destino"] == "Marabá - PA" and sol["viagem_fim"] == ONTEM.isoformat()
    assert sol["centro_custo"] == "3350 - T.I / T.A"
    assert sol["valor_total"] == "350.00"  # 2 x 135 + 1 x 80
    assert sol["alerta_limite"] is None and sol["despesas"] == []
    linhas = [
        (x["tipo_rotulo"], x["quantidade"], x["valor_unitario"], x["subtotal"])
        for x in sol["linhas_diaria"]
    ]
    assert linhas == [
        ("Valor Integral", 2, "135.00", "270.00"),
        ("Valor Parcial", 1, "80.00", "80.00"),
    ]

    assert decidir(cenario, sol["id"], "conferir", THAIS, "financeiro").json()["status"] == (
        "aguardando_gestor"
    )
    assert decidir(cenario, sol["id"], "aprovar", GESTOR, "gestor").json()["status"] == (
        "aguardando_pagamento"
    )
    entrar(cenario, THAIS, "financeiro")
    r = cenario.post(f"/api/solicitacoes/{sol['id']}/pagar", json={"data_pagamento": "2026-10-09"})
    assert r.json()["status"] == "pago"


def test_valor_integral_vem_do_servidor(cenario):
    """O cliente não manda o valor da integral: mesmo que mande, vale o da política."""
    linha = {"tipo": "integral", "quantidade": 1, "valor": "1,00"}
    sol = criar_viagem(cenario, [linha])
    assert sol["valor_total"] == "135.00"


def test_misturar_integral_e_parcial_sem_teto_na_parcial(cenario):
    sol = criar_viagem(cenario, [parcial(1, "500,00"), integral(1), parcial(1, "0,50")])
    assert sol["valor_total"] == "635.50"


def test_viagem_internacional_nao_tem_diaria(cenario):
    entrar(cenario, COLAB, "", "Colab")
    r = cenario.post("/api/solicitacoes/viagem", json=pedido_diaria(internacional=True))
    assert r.status_code == 400 and "internacional não tem diária" in r.json()["detail"]


def test_gestor_pedindo_pula_aprovacao(cenario):
    entrar(cenario, GESTOR, "gestor", "Gestor")
    cenario.put("/api/perfil", json={"matricula": "77"})
    r = cenario.post("/api/solicitacoes/viagem", json=pedido_diaria(gestor=None))
    assert r.status_code == 201, r.text
    sol = r.json()
    assert sol["pula_gestor"] is True
    r = decidir(cenario, sol["id"], "conferir", THAIS, "financeiro")
    assert r.json()["status"] == "aguardando_pagamento"


def test_alerta_quando_ha_mais_diarias_que_dias(cenario):
    sol = criar_viagem(cenario, [integral(4)])  # a viagem tem 3 dias
    assert "(4) maior que os dias da viagem (3)" in sol["alerta_limite"]
    assert criar_viagem(cenario, [integral(3)])["alerta_limite"] is None


def test_alerta_total_acima_do_limite(cenario):
    sol = criar_viagem(cenario, [integral(1), parcial(1, "5.000,00")])
    assert "Total acima do limite" in sol["alerta_limite"]


@pytest.mark.parametrize(
    ("linhas", "extra", "mensagem"),
    [
        ([], {}, "pelo menos uma linha"),
        ([{"tipo": "", "quantidade": 1}], {}, "Valor Integral ou Valor Parcial"),
        ([{"tipo": "outro", "quantidade": 1}], {}, "Valor Integral ou Valor Parcial"),
        ([integral(0)], {}, "quantidade de diárias"),
        ([integral(61)], {}, "quantidade de diárias"),
        ([parcial(1, "")], {}, "valor da diária parcial"),
        ([parcial(1, "0")], {}, "maior que zero"),
        ([parcial(1, "abc")], {}, "Valor inválido"),
        ([integral()] * 11, {}, "Máximo de 10 linhas"),
        (
            None,
            {"viagem_inicio": ONTEM.isoformat(), "viagem_fim": VIAGEM_INICIO.isoformat()},
            "fim da viagem",
        ),
        (None, {"destino": " "}, "destino"),
        (None, {"descricao": ""}, "motivo da viagem"),
        (None, {"empresa_id": 999}, "Empresa de débito inválida"),
        (None, {"centro_custo_id": ""}, "entro de custo"),
        (None, {"gestor_email": COLAB}, "seu próprio aprovador"),
    ],
)
def test_validacoes(cenario, linhas, extra, mensagem):
    entrar(cenario, COLAB, "", "Colab")
    r = cenario.post("/api/solicitacoes/viagem", json=pedido_diaria(linhas, **extra))
    assert r.status_code == 400 and mensagem in r.json()["detail"], r.text


def test_outro_colaborador_nao_ve(cenario):
    sol = criar_viagem(cenario)
    entrar(cenario, "outro@tecnored.com.br", "", "Outro")
    assert cenario.get(f"/api/solicitacoes/{sol['id']}").status_code in (403, 404)


def test_correcao_troca_as_linhas(cenario):
    sol = criar_viagem(cenario)
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro", False, "Faltou uma diária")
    entrar(cenario, COLAB, "", "Colab")
    assert cenario.get(f"/api/solicitacoes/{sol['id']}").json()["acoes"] == ["reenviar"]
    r = cenario.post(
        f"/api/solicitacoes/{sol['id']}/reenviar-viagem",
        json=pedido_diaria([integral(3)], centro_custo_id="2"),
    )
    assert r.status_code == 200, r.text
    nova = r.json()
    assert nova["status"] == "em_conferencia" and nova["valor_total"] == "405.00"
    assert [(x["tipo"], x["quantidade"]) for x in nova["linhas_diaria"]] == [("integral", 3)]
    assert nova["centro_custo"] == "4110 - CONTROLADORIA" and nova["motivo_devolucao"] is None


def test_correcao_valida_como_o_pedido(cenario):
    sol = criar_viagem(cenario)
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro", False, "Corrigir")
    entrar(cenario, COLAB, "", "Colab")
    r = cenario.post(f"/api/solicitacoes/{sol['id']}/reenviar-viagem", json=pedido_diaria([]))
    assert r.status_code == 400 and "pelo menos uma linha" in r.json()["detail"]


def test_pedido_antigo_com_notas_abre_mas_nao_corrige(cenario, db):
    """Viagem de antes de 15/10 (com notas): continua visível; a correção pede pedido novo."""
    sol = criar_viagem(cenario)
    linha = db.get(Solicitacao, sol["id"])
    linha.linhas_diaria.clear()
    linha.despesas.append(
        Despesa(
            categoria="hospedagem",
            data_despesa=ONTEM,
            valor=linha.valor_total,
            arquivo_chave="x",
            arquivo_nome="hotel.pdf",
            arquivo_tipo="application/pdf",
            arquivo_tamanho=10,
            criado_em=linha.enviado_em,
        )
    )
    linha.status = "devolvido"
    db.commit()
    entrar(cenario, COLAB, "", "Colab")
    antigo = cenario.get(f"/api/solicitacoes/{sol['id']}").json()
    assert antigo["linhas_diaria"] == [] and len(antigo["despesas"]) == 1
    r = cenario.post(f"/api/solicitacoes/{sol['id']}/reenviar-viagem", json=pedido_diaria())
    assert r.status_code == 400 and "modelo antigo" in r.json()["detail"]


def test_rota_de_correcao_da_diaria_nao_serve_para_outros_tipos(cenario):
    entrar(cenario, COLAB, "", "Colab")
    alimentacao = enviar_alimentacao(cenario).json()
    r = cenario.post(f"/api/solicitacoes/{alimentacao['id']}/reenviar-viagem", json=pedido_diaria())
    assert r.status_code == 400


def test_cadastros_trazem_categorias(cenario):
    entrar(cenario, COLAB, "", "Colab")
    dados = cenario.get("/api/cadastros").json()
    ids = [c["id"] for c in dados["categorias_viagem"]]
    assert len(ids) == 16 and ids[0] == "refeicao"
    assert {"taxi_uber", "quilometragem", "despesas_diversas", "hospedagem"} <= set(ids)
    rotulos = {c["id"]: c["rotulo"] for c in dados["categorias_viagem"]}
    assert rotulos["refeicao"] == "Refeição - Nacional"
    assert dados["limite_solicitacao"] == "5000.00"


def test_alimentacao_usa_as_categorias_das_notas(cenario):
    entrar(cenario, COLAB, "", "Colab")
    sol = enviar_alimentacao(cenario).json()
    assert sol["tipo_rotulo"] == "Alimentação"
    assert sol["destino"] is None and sol["viagem_inicio"] is None
    assert sol["despesas"][0]["categoria_rotulo"] == "Refeição - Nacional"
