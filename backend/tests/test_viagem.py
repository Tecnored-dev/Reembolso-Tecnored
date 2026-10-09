"""Reembolso de viagem: várias notas, mesmo fluxo da alimentação."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import Despesa
from app.storage import ArquivoNaoEncontrado
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


def campos(notas, gestor=GESTOR, **extra):
    dados = {
        "destino": extra.get("destino", "Marabá - PA"),
        "viagem_inicio": extra.get("viagem_inicio", (HOJE - timedelta(days=3)).isoformat()),
        "viagem_fim": extra.get("viagem_fim", ONTEM.isoformat()),
        "descricao": extra.get("descricao", "Visita técnica à planta"),
        "empresa_id": "1",
        "despesas": json.dumps(notas),
    }
    if gestor:
        dados["gestor_email"] = gestor
    return dados


def enviar_viagem(cliente, notas, arquivos, rota="/api/solicitacoes/viagem", **extra):
    files = [("arquivos", (nome, conteudo, tipo)) for nome, conteudo, tipo in arquivos]
    return cliente.post(rota, data=campos(notas, **extra), files=files or None)


TRES_NOTAS = [
    nota("refeicao", "45,90", arquivo=0),
    nota("hospedagem", "320,00", arquivo=1),
    nota("transporte", "88,10", arquivo=2, descricao="Táxi aeroporto"),
]
TRES_ARQUIVOS = [
    ("almoco.jpg", JPG, "image/jpeg"),
    ("hotel.pdf", PDF, "application/pdf"),
    ("taxi.png", PNG, "image/png"),
]


def criar_viagem(cliente, notas=None, arquivos=None, **extra) -> dict:
    entrar(cliente, COLAB, "", "Colab")
    r = enviar_viagem(cliente, notas or TRES_NOTAS, arquivos or TRES_ARQUIVOS, **extra)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
def test_fluxo_completo_com_tres_notas(cenario):
    sol = criar_viagem(cenario)
    assert sol["tipo"] == "viagem" and sol["tipo_rotulo"] == "Viagem"
    assert sol["status"] == "em_conferencia"
    assert sol["destino"] == "Marabá - PA"
    assert sol["viagem_fim"] == ONTEM.isoformat()
    assert sol["valor_total"] == "454.00"
    assert sol["alerta_limite"] is None
    cats = [(d["categoria"], d["categoria_rotulo"], d["valor"]) for d in sol["despesas"]]
    assert cats == [
        ("refeicao", "Refeição", "45.90"),
        ("hospedagem", "Hospedagem", "320.00"),
        ("transporte", "Transporte / translado", "88.10"),
    ]
    assert sol["despesas"][2]["descricao"] == "Táxi aeroporto"

    # Cada nota abre com o tipo certo.
    tipos = []
    for d in sol["despesas"]:
        r = cenario.get(f"/api/solicitacoes/{sol['id']}/despesas/{d['id']}/arquivo")
        assert r.status_code == 200
        tipos.append(r.headers["content-type"])
    assert tipos == ["image/jpeg", "application/pdf", "image/png"]

    assert decidir(cenario, sol["id"], "conferir", THAIS, "financeiro").json()["status"] == (
        "aguardando_gestor"
    )
    assert decidir(cenario, sol["id"], "aprovar", GESTOR, "gestor").json()["status"] == (
        "aguardando_pagamento"
    )
    entrar(cenario, THAIS, "financeiro")
    r = cenario.post(f"/api/solicitacoes/{sol['id']}/pagar", json={"data_pagamento": "2026-10-09"})
    assert r.json()["status"] == "pago"


def test_gestor_pedindo_pula_aprovacao(cenario):
    entrar(cenario, GESTOR, "gestor", "Gestor")
    cenario.put("/api/perfil", json={"matricula": "77", "centro_custo_id": 1})
    r = enviar_viagem(cenario, TRES_NOTAS, TRES_ARQUIVOS, gestor=None)
    assert r.status_code == 201, r.text
    sol = r.json()
    assert sol["pula_gestor"] is True
    r = decidir(cenario, sol["id"], "conferir", THAIS, "financeiro")
    assert r.json()["status"] == "aguardando_pagamento"


def test_alerta_refeicao_soma_notas_do_mesmo_dia(cenario):
    notas = [
        nota("refeicao", "80,00", dia=ONTEM, arquivo=0),
        nota("refeicao", "70,00", dia=ONTEM, arquivo=1),
        nota("refeicao", "130,00", dia=HOJE - timedelta(days=2), arquivo=2),
    ]
    sol = criar_viagem(cenario, notas)
    assert "Refeição acima do limite diário" in sol["alerta_limite"]
    assert f"{ONTEM:%d/%m}" in sol["alerta_limite"]
    assert f"{HOJE - timedelta(days=2):%d/%m}" not in sol["alerta_limite"]


def test_hospedagem_cara_nao_gera_alerta_de_refeicao(cenario):
    notas = [nota("hospedagem", "400,00", arquivo=0)]
    sol = criar_viagem(cenario, notas, [TRES_ARQUIVOS[0]])
    assert sol["alerta_limite"] is None


def test_alerta_total_acima_do_limite(cenario):
    notas = [nota("hospedagem", "3000,00", arquivo=0), nota("transporte", "2500,00", arquivo=1)]
    sol = criar_viagem(cenario, notas, TRES_ARQUIVOS[:2])
    assert "Total acima do limite por solicitação" in sol["alerta_limite"]
    assert sol["valor_total"] == "5500.00"


@pytest.mark.parametrize(
    ("notas", "arquivos", "extra", "mensagem"),
    [
        ([], [], {}, "pelo menos uma nota"),
        ([nota(arquivo=None)], [], {}, "Nota 1: anexe"),
        ([nota(arquivo=3)], TRES_ARQUIVOS[:1], {}, "Nota 1: arquivo inválido"),
        ([nota(arquivo=0), nota(arquivo=0)], TRES_ARQUIVOS[:1], {}, "Nota 2: arquivo inválido"),
        ([nota("bebida", arquivo=0)], TRES_ARQUIVOS[:1], {}, "Nota 1: categoria inválida"),
        ([nota("outros", arquivo=0)], TRES_ARQUIVOS[:1], {}, "Outros"),
        (
            [nota(dia=HOJE + timedelta(days=1), arquivo=0)],
            TRES_ARQUIVOS[:1],
            {},
            "Nota 1: a data não pode ser no futuro",
        ),
        ([nota(valor="0", arquivo=0)], TRES_ARQUIVOS[:1], {}, "Nota 1: O valor"),
        (
            [nota(arquivo=0)],
            TRES_ARQUIVOS[:1],
            {"viagem_inicio": ONTEM.isoformat(), "viagem_fim": (ONTEM - timedelta(1)).isoformat()},
            "fim da viagem",
        ),
        ([nota(arquivo=0)], TRES_ARQUIVOS[:1], {"destino": "  "}, "destino"),
        ([nota(arquivo=0)], TRES_ARQUIVOS[:1], {"descricao": ""}, "motivo da viagem"),
        (
            [nota(arquivo=0)],
            [("nota.docx", b"PK\x03\x04" + b"0" * 50, "application/octet-stream")],
            {},
            "Arquivo 1 (nota.docx): Formato não aceito",
        ),
        ([nota(arquivo=0, id=999)], TRES_ARQUIVOS[:1], {}, "Nota 1: nota inválida"),
    ],
)
def test_validacoes(cenario, notas, arquivos, extra, mensagem):
    entrar(cenario, COLAB, "", "Colab")
    r = enviar_viagem(cenario, notas, arquivos, **extra)
    assert r.status_code == 400, r.text
    assert mensagem in r.json()["detail"]


def test_lista_de_notas_malformada(cenario):
    entrar(cenario, COLAB, "", "Colab")
    dados = campos([])
    dados["despesas"] = "isto não é json"
    r = cenario.post("/api/solicitacoes/viagem", data=dados)
    assert r.status_code == 400 and "Lista de notas inválida" in r.json()["detail"]


def test_outro_colaborador_nao_ve(cenario):
    sol = criar_viagem(cenario)
    entrar(cenario, "intruso@tecnored.com.br")
    assert cenario.get(f"/api/solicitacoes/{sol['id']}").status_code == 404
    d = sol["despesas"][0]["id"]
    assert cenario.get(f"/api/solicitacoes/{sol['id']}/despesas/{d}/arquivo").status_code == 404


def _chaves(db, sol_id):
    return {
        d.id: d.arquivo_chave for d in db.scalars(select(Despesa).filter_by(solicitacao_id=sol_id))
    }


def test_correcao_mantem_troca_remove_e_adiciona_notas(cenario, db):
    sol = criar_viagem(cenario)
    n1, n2, n3 = (d["id"] for d in sol["despesas"])
    antes = _chaves(db, sol["id"])
    decidir(
        cenario,
        sol["id"],
        "conferir",
        THAIS,
        "financeiro",
        aprovar=False,
        comentario="Falta o recibo do hotel",
    )

    entrar(cenario, COLAB, "", "Colab")
    notas = [
        nota("refeicao", "40,00", id=n1),  # mantém a nota, muda o valor
        nota("hospedagem", "320,00", id=n2, arquivo=0),  # troca a nota
        nota("lavanderia", "25,00", arquivo=1),  # nota nova
    ]  # a n3 (táxi) sai
    r = enviar_viagem(
        cenario,
        notas,
        [("recibo.pdf", PDF, "application/pdf"), ("lav.jpg", JPG, "image/jpeg")],
        rota=f"/api/solicitacoes/{sol['id']}/reenviar-viagem",
        destino="Marabá - PA (planta 2)",
    )
    assert r.status_code == 200, r.text
    nova = r.json()
    assert nova["status"] == "em_conferencia"
    assert nova["destino"] == "Marabá - PA (planta 2)"
    assert nova["valor_total"] == "385.00"
    assert [d["categoria"] for d in nova["despesas"]] == ["refeicao", "hospedagem", "lavanderia"]
    assert nova["despesas"][1]["arquivo_nome"] == "recibo.pdf"

    depois = _chaves(db, sol["id"])
    assert depois[n1] == antes[n1]
    assert depois[n2] != antes[n2]
    assert n3 not in depois
    storage = cenario.storage
    for removida in (antes[n2], antes[n3]):
        with pytest.raises(ArquivoNaoEncontrado):
            storage.abrir(removida)
    for chave in depois.values():
        assert storage.abrir(chave)


def test_correcao_exige_arquivo_em_nota_nova(cenario):
    sol = criar_viagem(cenario)
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro", aprovar=False, comentario="Ajuste")
    entrar(cenario, COLAB, "", "Colab")
    notas = [nota(id=sol["despesas"][0]["id"]), nota("outros", descricao="Estacionamento")]
    r = enviar_viagem(cenario, notas, [], rota=f"/api/solicitacoes/{sol['id']}/reenviar-viagem")
    assert r.status_code == 400 and "Nota 2: anexe" in r.json()["detail"]


def test_correcao_nao_aceita_nota_de_outra_solicitacao(cenario):
    a = criar_viagem(cenario)
    b = criar_viagem(cenario)
    decidir(cenario, a["id"], "conferir", THAIS, "financeiro", aprovar=False, comentario="Ajuste")
    entrar(cenario, COLAB, "", "Colab")
    notas = [nota(id=b["despesas"][0]["id"])]
    r = enviar_viagem(cenario, notas, [], rota=f"/api/solicitacoes/{a['id']}/reenviar-viagem")
    assert r.status_code == 400 and "Nota 1: nota inválida" in r.json()["detail"]


def test_rotas_de_correcao_nao_se_misturam(cenario):
    viagem = criar_viagem(cenario)
    entrar(cenario, COLAB, "", "Colab")
    alimentacao = enviar_alimentacao(cenario).json()
    for sol in (viagem, alimentacao):
        decidir(
            cenario, sol["id"], "conferir", THAIS, "financeiro", aprovar=False, comentario="Ajuste"
        )
    entrar(cenario, COLAB, "", "Colab")

    r = cenario.post(
        f"/api/solicitacoes/{viagem['id']}/reenviar",
        data={
            "data_despesa": ONTEM.isoformat(),
            "valor": "10",
            "descricao": "x",
            "empresa_id": "1",
            "gestor_email": GESTOR,
        },
    )
    assert r.status_code == 400 and "não é de alimentação" in r.json()["detail"]

    r = enviar_viagem(
        cenario,
        [nota(arquivo=0)],
        TRES_ARQUIVOS[:1],
        rota=f"/api/solicitacoes/{alimentacao['id']}/reenviar-viagem",
    )
    assert r.status_code == 400 and "não é de viagem" in r.json()["detail"]


def test_cadastros_trazem_categorias(cenario):
    entrar(cenario, COLAB, "", "Colab")
    dados = cenario.get("/api/cadastros").json()
    assert [c["id"] for c in dados["categorias_viagem"]] == [
        "refeicao",
        "hospedagem",
        "transporte",
        "lavanderia",
        "outros",
    ]
    assert dados["limite_solicitacao"] == "5000.00"


def test_alimentacao_continua_com_categoria_refeicao(cenario):
    entrar(cenario, COLAB, "", "Colab")
    sol = enviar_alimentacao(cenario).json()
    assert sol["tipo_rotulo"] == "Alimentação"
    assert sol["destino"] is None and sol["viagem_inicio"] is None
    assert sol["despesas"][0]["categoria_rotulo"] == "Refeição"
