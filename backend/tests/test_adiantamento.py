"""Adiantamento de viagem: diárias pagas antes e prestação de contas depois."""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Despesa, Notificacao, Solicitacao
from app.services.fluxo import calcular_diarias, processar_expiracoes
from app.storage import ArquivoNaoEncontrado
from tests.test_alimentacao import (
    COLAB,
    GESTOR,
    JPG,
    PDF,
    THAIS,
    completar_perfil,
    decidir,
    entrar,
)
from tests.test_alimentacao import cenario as cenario  # fixture reaproveitada
from tests.test_viagem import TRES_ARQUIVOS, TRES_NOTAS, criar_viagem, nota, pedido_diaria

HOJE = date.today()
INICIO = HOJE - timedelta(days=4)
FIM = HOJE - timedelta(days=2)
VALOR = "405,00"  # o colaborador informa o valor (Thais, 15/10); sem cálculo por dia


def pedido(gestor=GESTOR, **extra) -> dict:
    dados = {
        "destino": "Marabá - PA",
        "viagem_inicio": INICIO.isoformat(),
        "viagem_fim": FIM.isoformat(),
        "descricao": "Visita técnica à planta",
        "empresa_id": 1,
        "valor": VALOR,
        **extra,
    }
    if gestor:
        dados.setdefault("gestor_email", gestor)
    return dados


def criar_adiantamento(cliente, quem=COLAB, papeis="", **extra) -> dict:
    entrar(cliente, quem, papeis)
    r = cliente.post("/api/solicitacoes/adiantamento", json=pedido(**extra))
    assert r.status_code == 201, r.text
    return r.json()


def pagar(cliente, sol_id, dia=HOJE):
    entrar(cliente, THAIS, "financeiro")
    r = cliente.post(f"/api/solicitacoes/{sol_id}/pagar", json={"data_pagamento": dia.isoformat()})
    assert r.status_code == 200, r.text
    return r.json()


def adiantamento_pago(cliente) -> dict:
    sol = criar_adiantamento(cliente)
    assert decidir(cliente, sol["id"], "aprovar", GESTOR, "gestor").status_code == 200
    return pagar(cliente, sol["id"])


def prestar(cliente, sol_id, notas, arquivos):
    entrar(cliente, COLAB, "")
    files = [("arquivos", a) for a in arquivos]
    return cliente.post(
        f"/api/solicitacoes/{sol_id}/prestacao",
        data={"despesas": json.dumps(notas)},
        files=files or None,
    )


def prestacao_conferida(cliente, valores: list[str]) -> dict:
    sol = adiantamento_pago(cliente)
    notas = [nota("refeicao", v, arquivo=i) for i, v in enumerate(valores)]
    arquivos = [(f"n{i}.jpg", JPG, "image/jpeg") for i in range(len(valores))]
    r = prestar(cliente, sol["id"], notas, arquivos)
    assert r.status_code == 200, r.text
    r = decidir(cliente, sol["id"], "conferir", THAIS, "financeiro")
    assert r.status_code == 200, r.text
    return r.json()


def enviar_comprovante(cliente, sol_id, dia=HOJE, arquivo=("pix.pdf", PDF, "application/pdf")):
    entrar(cliente, COLAB, "")
    return cliente.post(
        f"/api/solicitacoes/{sol_id}/comprovante",
        data={"data_transferencia": dia.isoformat()},
        files={"arquivo": arquivo} if arquivo else None,
    )


def avisos(db, sol_id) -> list[Notificacao]:
    return list(db.scalars(select(Notificacao).where(Notificacao.solicitacao_id == sol_id)).all())


# ---------------------------------------------------------------------------
# Pedido
# ---------------------------------------------------------------------------
def test_contagem_de_diarias():
    assert calcular_diarias(date(2026, 10, 5), date(2026, 10, 7)) == 3
    assert calcular_diarias(date(2026, 10, 5), date(2026, 10, 5)) == 1
    assert calcular_diarias(date(2026, 9, 30), date(2026, 10, 1)) == 2


def test_pedido_com_valor_informado_vai_para_o_gestor(cenario, db):
    sol = criar_adiantamento(cenario)
    assert sol["tipo"] == "adiantamento" and sol["tipo_rotulo"] == "Adiantamento"
    assert sol["status"] == "aguardando_gestor"
    # Valor informado pelo colaborador, sem cálculo por dia (Thais, 15/10).
    assert sol["valor_total"] == "405.00" and sol["diarias"] is None
    assert sol["valor_complementar"] is None and sol["centro_custo"] is None
    assert sol["despesas"] == [] and sol["valor_gasto"] is None and sol["saldo"] is None
    assert sol["empresa"] == "TECNORED" and sol["destino"] == "Marabá - PA"
    aviso = avisos(db, sol["id"])[0]
    assert aviso.para == GESTOR and "R$ 405,00" in aviso.corpo


def test_valor_nao_depende_dos_dias_da_viagem(cenario):
    sol = criar_adiantamento(
        cenario,
        valor="1.234,56",
        viagem_inicio=(HOJE + timedelta(days=10)).isoformat(),
        viagem_fim=(HOJE + timedelta(days=30)).isoformat(),
    )
    assert sol["valor_total"] == "1234.56" and sol["diarias"] is None


def test_viagem_internacional_pode_ter_adiantamento(cenario):
    sol = criar_adiantamento(cenario, destino="Lisboa - Portugal", valor="6000,00")
    assert sol["valor_total"] == "6000.00"
    assert "Total acima do limite" in sol["alerta_limite"]


@pytest.mark.parametrize(
    ("extra", "mensagem"),
    [
        ({"destino": ""}, "Informe o destino"),
        ({"descricao": "  "}, "motivo da viagem"),
        ({"viagem_inicio": HOJE.isoformat(), "viagem_fim": INICIO.isoformat()}, "antes do início"),
        ({"valor": ""}, "valor do adiantamento"),
        ({"valor": "0"}, "maior que zero"),
        ({"valor": "-10"}, "maior que zero"),
        ({"valor": "abc"}, "Valor inválido"),
        ({"valor": "9.999.999,00"}, "acima do máximo"),
        ({"empresa_id": 999}, "Empresa de débito inválida"),
        ({"gestor_email": "ninguem@tecnored.com.br"}, "Gestor não encontrado"),
        ({"gestor_email": COLAB}, "seu próprio aprovador"),
    ],
)
def test_validacoes_do_pedido(cenario, extra, mensagem):
    entrar(cenario, COLAB, "")
    r = cenario.post("/api/solicitacoes/adiantamento", json=pedido(**extra))
    assert r.status_code == 400 and mensagem in r.json()["detail"], r.text


def test_sem_gestor_recusa(cenario):
    entrar(cenario, COLAB, "")
    r = cenario.post("/api/solicitacoes/adiantamento", json=pedido(gestor=None))
    assert r.status_code == 400 and "Escolha o gestor" in r.json()["detail"]


def test_perfil_obrigatorio(cenario):
    entrar(cenario, "novo@tecnored.com.br", "")
    r = cenario.post("/api/solicitacoes/adiantamento", json=pedido())
    assert r.status_code == 400 and "Complete seu perfil" in r.json()["detail"]


def test_gestor_pedindo_vai_direto_para_pagamento(cenario, db):
    entrar(cenario, GESTOR, "gestor")
    completar_perfil(cenario)
    r = cenario.post("/api/solicitacoes/adiantamento", json=pedido(gestor=None))
    assert r.status_code == 201, r.text
    sol = r.json()
    assert sol["status"] == "aguardando_pagamento" and sol["pula_gestor"] is True
    assert sol["gestor_nome"] is None
    assert [n.para for n in avisos(db, sol["id"])] == [THAIS]


def devolvido_antigo(db, sol_id: int) -> None:
    """Pedido devolvido pelo gestor ANTES de 15/10 (hoje o gestor só recusa)."""
    sol = db.get(Solicitacao, sol_id)
    sol.status, sol.devolvido_por, sol.motivo_devolucao = "devolvido", "Gestor", "Volta antes"
    db.commit()


def test_gestor_recusa_e_o_pedido_termina(cenario):
    sol = criar_adiantamento(cenario)
    entrar(cenario, GESTOR, "gestor")
    assert cenario.get(f"/api/solicitacoes/{sol['id']}").json()["acoes"] == [
        "aprovar",
        "recusar",
    ]
    r = decidir(cenario, sol["id"], "aprovar", GESTOR, "gestor", aprovar=False)
    assert r.status_code == 400 and "motivo da recusa" in r.json()["detail"]
    r = decidir(cenario, sol["id"], "aprovar", GESTOR, "gestor", False, "Viagem cancelada")
    recusado = r.json()
    assert recusado["status"] == "recusado"
    assert recusado["status_rotulo"] == "Finalizado - Recusado"
    assert recusado["recusado_por"] == "gestor" and recusado["motivo_recusa"] == "Viagem cancelada"

    entrar(cenario, COLAB, "")
    assert cenario.get(f"/api/solicitacoes/{sol['id']}").json()["acoes"] == []
    r = cenario.post(f"/api/solicitacoes/{sol['id']}/reenviar-adiantamento", json=pedido())
    assert r.status_code == 400


def test_pedido_devolvido_antes_da_mudanca_ainda_pode_ser_corrigido(cenario, db):
    sol = criar_adiantamento(cenario)
    devolvido_antigo(db, sol["id"])
    entrar(cenario, COLAB, "")
    assert cenario.get(f"/api/solicitacoes/{sol['id']}").json()["acoes"] == ["reenviar"]
    novo_fim = (FIM - timedelta(days=1)).isoformat()
    r = cenario.post(
        f"/api/solicitacoes/{sol['id']}/reenviar-adiantamento",
        json=pedido(viagem_fim=novo_fim, valor="270,00"),
    )
    assert r.status_code == 200, r.text
    corrigida = r.json()
    # Sem conferência no adiantamento: o reenvio volta para o gestor.
    assert corrigida["status"] == "aguardando_gestor"
    assert corrigida["valor_total"] == "270.00" and corrigida["diarias"] is None
    assert corrigida["motivo_devolucao"] is None


def test_thais_nao_confere_o_pedido_e_paga_sem_nota(cenario):
    sol = criar_adiantamento(cenario)
    r = decidir(cenario, sol["id"], "conferir", THAIS, "financeiro")
    assert r.status_code == 400  # não há conferência no pedido
    r = cenario.post(f"/api/solicitacoes/{sol['id']}/pagar", json={"data_pagamento": "2026-10-01"})
    assert r.status_code == 400  # nem paga antes do gestor
    decidir(cenario, sol["id"], "aprovar", GESTOR, "gestor")
    pago = pagar(cenario, sol["id"])
    assert pago["status"] == "aguardando_prestacao"
    assert pago["status_rotulo"] == "Paga — aguardando prestação de contas"
    entrar(cenario, COLAB, "")
    assert cenario.get(f"/api/solicitacoes/{sol['id']}").json()["acoes"] == ["prestar_contas"]


def test_rotas_de_outros_tipos_nao_servem_para_adiantamento(cenario, db):
    sol = criar_adiantamento(cenario)
    devolvido_antigo(db, sol["id"])
    entrar(cenario, COLAB, "")
    r = cenario.post(
        f"/api/solicitacoes/{sol['id']}/reenviar-viagem",
        json=pedido_diaria(),
    )
    assert r.status_code == 400 and "não é de diária" in r.json()["detail"]
    viagem = criar_viagem(cenario)
    decidir(cenario, viagem["id"], "conferir", THAIS, "financeiro", False, "Corrigir")
    entrar(cenario, COLAB, "")
    r = cenario.post(f"/api/solicitacoes/{viagem['id']}/reenviar-adiantamento", json=pedido())
    assert r.status_code == 400 and "não é de adiantamento" in r.json()["detail"]
    r = prestar(cenario, viagem["id"], TRES_NOTAS, TRES_ARQUIVOS)
    assert r.status_code == 400 and "não é de adiantamento" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Prestação de contas
# ---------------------------------------------------------------------------
def test_prestacao_so_depois_do_pagamento(cenario):
    sol = criar_adiantamento(cenario)
    r = prestar(cenario, sol["id"], [nota(arquivo=0)], [("n.jpg", JPG, "image/jpeg")])
    assert r.status_code == 400 and "a ação não se aplica" in r.json()["detail"]


def test_prestacao_so_de_quem_pediu(cenario):
    sol = adiantamento_pago(cenario)
    entrar(cenario, "intruso@tecnored.com.br", "")
    r = cenario.post(
        f"/api/solicitacoes/{sol['id']}/prestacao",
        data={"despesas": json.dumps([nota(arquivo=0)])},
        files=[("arquivos", ("n.jpg", JPG, "image/jpeg"))],
    )
    assert r.status_code == 404
    # O gestor vê, mas não presta contas no lugar do colaborador.
    entrar(cenario, GESTOR, "gestor")
    r = cenario.post(
        f"/api/solicitacoes/{sol['id']}/prestacao",
        data={"despesas": json.dumps([nota(arquivo=0)])},
        files=[("arquivos", ("n.jpg", JPG, "image/jpeg"))],
    )
    assert r.status_code == 403


def test_prestacao_valida_notas_como_no_reembolso(cenario):
    sol = adiantamento_pago(cenario)
    r = prestar(cenario, sol["id"], [], [])
    assert "pelo menos uma nota" in r.json()["detail"]
    r = prestar(cenario, sol["id"], [nota()], [])
    assert "Nota 1: anexe" in r.json()["detail"]
    r = prestar(
        cenario, sol["id"], [nota("despesas_diversas", arquivo=0)], [("n.jpg", JPG, "image/jpeg")]
    )
    assert "Despesas diversas" in r.json()["detail"]
    amanha = HOJE + timedelta(days=1)
    r = prestar(cenario, sol["id"], [nota(dia=amanha, arquivo=0)], [("n.jpg", JPG, "image/jpeg")])
    assert "futuro" in r.json()["detail"]
    r = prestar(cenario, sol["id"], [nota(arquivo=0)], [("n.jpg", b"texto", "image/jpeg")])
    assert "Formato não aceito" in r.json()["detail"]
    entrar(cenario, COLAB, "")
    r = cenario.post(f"/api/solicitacoes/{sol['id']}/prestacao", data={"despesas": "[{oops"})
    assert "Lista de notas inválida" in r.json()["detail"]


def test_sobra_devolucao_e_encerramento(cenario, db):
    sol = adiantamento_pago(cenario)  # R$ 405,00
    r = prestar(cenario, sol["id"], TRES_NOTAS, TRES_ARQUIVOS)  # 45,90 + 320 + 88,10 = 454
    assert r.status_code == 200, r.text
    # troca para gastar menos: só a hospedagem
    assert r.json()["status"] == "prestacao_em_conferencia"
    assert r.json()["valor_gasto"] == "454.00" and r.json()["saldo"] == "-49.00"

    r = decidir(cenario, sol["id"], "conferir", THAIS, "financeiro", False, "Táxi sem nota fiscal")
    assert r.json()["status"] == "prestacao_devolvida"
    entrar(cenario, COLAB, "")
    atual = cenario.get(f"/api/solicitacoes/{sol['id']}").json()
    assert atual["acoes"] == ["prestar_contas"]
    ids = [d["id"] for d in atual["despesas"]]
    r = prestar(
        cenario,
        sol["id"],
        [nota("refeicao", "45,90", id=ids[0]), nota("hospedagem", "320,00", id=ids[1])],
        [],
    )
    assert r.status_code == 200, r.text
    assert r.json()["valor_gasto"] == "365.90" and r.json()["saldo"] == "39.10"
    assert len(r.json()["despesas"]) == 2

    r = decidir(cenario, sol["id"], "conferir", THAIS, "financeiro")
    conferida = r.json()
    assert conferida["status"] == "aguardando_devolucao"
    assert conferida["prestacao_conferida_por"] == "thais"

    # resumo para a Thais e para o gestor
    resumos = [n for n in avisos(db, sol["id"]) if "Resumo da prestação" in n.assunto]
    assert sorted(n.para for n in resumos) == [GESTOR, THAIS]
    assert "Sobrou R$ 39,10" in resumos[0].corpo

    # comprovante
    r = enviar_comprovante(cenario, sol["id"], arquivo=None)
    assert "Anexe o comprovante" in r.json()["detail"]
    r = enviar_comprovante(cenario, sol["id"], dia=HOJE + timedelta(days=1))
    assert "futuro" in r.json()["detail"]
    r = enviar_comprovante(cenario, sol["id"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "devolucao_em_conferencia"
    comp = [d for d in r.json()["despesas"] if d["categoria"] == "comprovante_devolucao"]
    assert len(comp) == 1 and comp[0]["valor"] == "39.10"
    assert comp[0]["categoria_rotulo"] == "Comprovante da devolução"
    # o comprovante não entra no gasto
    assert r.json()["valor_gasto"] == "365.90"

    entrar(cenario, THAIS, "financeiro")
    detalhe = cenario.get(f"/api/solicitacoes/{sol['id']}").json()
    assert detalhe["acoes"] == ["confirmar_devolucao", "recusar_comprovante"]
    r = cenario.post(f"/api/solicitacoes/{sol['id']}/confirmar-devolucao", json={"aprovar": True})
    final = r.json()
    assert final["status"] == "encerrado" and final["status_rotulo"] == "Encerrada"
    assert final["devolucao_confirmada_por"] == "thais" and final["encerrado_em"]
    assert final["acoes"] == []


def test_comprovante_recusado_e_trocado(cenario, db):
    sol = prestacao_conferida(cenario, ["100,00"])  # sobra 305,00
    assert sol["status"] == "aguardando_devolucao"
    enviar_comprovante(cenario, sol["id"], arquivo=("errado.pdf", PDF, "application/pdf"))
    primeira = db.scalar(
        select(Despesa.arquivo_chave).where(
            Despesa.solicitacao_id == sol["id"], Despesa.categoria == "comprovante_devolucao"
        )
    )
    entrar(cenario, THAIS, "financeiro")
    r = cenario.post(f"/api/solicitacoes/{sol['id']}/confirmar-devolucao", json={"aprovar": False})
    assert r.status_code == 400 and "Explique" in r.json()["detail"]
    r = cenario.post(
        f"/api/solicitacoes/{sol['id']}/confirmar-devolucao",
        json={"aprovar": False, "comentario": "Valor transferido não confere"},
    )
    assert r.json()["status"] == "aguardando_devolucao"
    assert r.json()["motivo_devolucao"] == "Valor transferido não confere"

    r = enviar_comprovante(cenario, sol["id"], arquivo=("certo.jpg", JPG, "image/jpeg"))
    comps = [d for d in r.json()["despesas"] if d["categoria"] == "comprovante_devolucao"]
    assert [c["arquivo_nome"] for c in comps] == ["certo.jpg"]
    with pytest.raises(ArquivoNaoEncontrado):
        cenario.storage.abrir(primeira)  # type: ignore[attr-defined]


def test_valor_exato_encerra_direto(cenario):
    sol = prestacao_conferida(cenario, ["200,00", "205,00"])
    assert sol["saldo"] == "0.00" and sol["status"] == "encerrado"


def test_gasto_a_mais_gestor_aprova_e_thais_paga_a_diferenca(cenario, db):
    sol = prestacao_conferida(cenario, ["300,00", "150,50"])  # gastou 450,50
    assert sol["status"] == "diferenca_aguardando_gestor" and sol["saldo"] == "-45.50"
    resumo = [n for n in avisos(db, sol["id"]) if n.para == GESTOR and "Resumo" in n.assunto]
    assert "precisa da sua aprovação" in resumo[0].corpo

    entrar(cenario, GESTOR, "gestor")
    assert "aprovar" in cenario.get(f"/api/solicitacoes/{sol['id']}").json()["acoes"]
    lista = cenario.get("/api/solicitacoes", params={"escopo": "aprovacao"}).json()
    assert [s["id"] for s in lista] == [sol["id"]]

    r = decidir(cenario, sol["id"], "aprovar", GESTOR, "gestor")
    assert r.json()["status"] == "diferenca_aguardando_pagamento"
    assert r.json()["diferenca_aprovada_por"] == "gestor"
    entrar(cenario, THAIS, "financeiro")
    lista = cenario.get("/api/solicitacoes", params={"escopo": "pagamento"}).json()
    assert sol["id"] in [s["id"] for s in lista]
    final = pagar(cenario, sol["id"], dia=HOJE)
    assert final["status"] == "encerrado"
    assert final["data_pagamento_diferenca"] == HOJE.isoformat()
    # a data do pagamento do adiantamento não é sobrescrita
    assert final["data_pagamento"] == HOJE.isoformat()


def test_gestor_recusa_a_diferenca_e_o_pedido_termina(cenario):
    sol = prestacao_conferida(cenario, ["500,00"])
    r = decidir(cenario, sol["id"], "aprovar", GESTOR, "gestor", False, "Hotel acima da política")
    assert r.json()["status"] == "recusado"
    assert r.json()["motivo_recusa"] == "Hotel acima da política"
    entrar(cenario, COLAB, "")
    assert cenario.get(f"/api/solicitacoes/{sol['id']}").json()["acoes"] == []


def test_gestor_com_gasto_a_mais_vai_direto_para_pagamento(cenario):
    entrar(cenario, GESTOR, "gestor")
    completar_perfil(cenario)
    r = cenario.post("/api/solicitacoes/adiantamento", json=pedido(gestor=None))
    sol = r.json()
    pagar(cenario, sol["id"])
    entrar(cenario, GESTOR, "gestor")
    r = cenario.post(
        f"/api/solicitacoes/{sol['id']}/prestacao",
        data={"despesas": json.dumps([nota("hospedagem", "500,00", arquivo=0)])},
        files=[("arquivos", ("n.jpg", JPG, "image/jpeg"))],
    )
    assert r.status_code == 200, r.text
    r = decidir(cenario, sol["id"], "conferir", THAIS, "financeiro")
    assert r.json()["status"] == "diferenca_aguardando_pagamento"


def test_filas_de_trabalho(cenario):
    sol = adiantamento_pago(cenario)
    prestar(cenario, sol["id"], [nota(arquivo=0)], [("n.jpg", JPG, "image/jpeg")])
    entrar(cenario, THAIS, "financeiro")
    fila = cenario.get("/api/solicitacoes", params={"escopo": "conferencia"}).json()
    assert sol["id"] in [s["id"] for s in fila]
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro")  # sobra
    enviar_comprovante(cenario, sol["id"])
    entrar(cenario, THAIS, "financeiro")
    fila = cenario.get("/api/solicitacoes", params={"escopo": "conferencia"}).json()
    assert sol["id"] in [s["id"] for s in fila]


def test_papeis_nas_etapas_novas(cenario):
    sol = prestacao_conferida(cenario, ["100,00"])
    # só quem pediu envia comprovante
    entrar(cenario, GESTOR, "gestor")
    r = cenario.post(
        f"/api/solicitacoes/{sol['id']}/comprovante",
        data={"data_transferencia": HOJE.isoformat()},
        files={"arquivo": ("p.pdf", PDF, "application/pdf")},
    )
    assert r.status_code == 403
    enviar_comprovante(cenario, sol["id"])
    # só o financeiro confirma
    for quem, papeis in [(COLAB, ""), (GESTOR, "gestor")]:
        entrar(cenario, quem, papeis)
        r = cenario.post(
            f"/api/solicitacoes/{sol['id']}/confirmar-devolucao", json={"aprovar": True}
        )
        assert r.status_code == 403
    # gestor não aprova o que não é dele / colaborador não aprova
    entrar(cenario, COLAB, "")
    r = cenario.post(f"/api/solicitacoes/{sol['id']}/aprovar", json={"aprovar": True})
    assert r.status_code == 403


def test_prestacao_devolvida_nao_expira(cenario, db, settings):
    """O dinheiro já foi pago: a prestação devolvida não é cancelada sozinha."""
    from datetime import datetime

    sol = adiantamento_pago(cenario)
    prestar(cenario, sol["id"], [nota(arquivo=0)], [("n.jpg", JPG, "image/jpeg")])
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro", False, "Faltou nota")
    resultado = processar_expiracoes(db, settings, agora=datetime(2030, 1, 1))
    assert resultado["cancelamentos"] == 0
    entrar(cenario, COLAB, "")
    assert cenario.get(f"/api/solicitacoes/{sol['id']}").json()["status"] == "prestacao_devolvida"


def test_pedido_devolvido_expira_como_os_outros(cenario, db, settings):
    from datetime import datetime

    sol = criar_adiantamento(cenario)
    devolvido_antigo(db, sol["id"])
    resultado = processar_expiracoes(db, settings, agora=datetime(2030, 1, 1))
    assert resultado["cancelamentos"] == 1


def test_cadastros_trazem_valor_da_diaria(cenario):
    entrar(cenario, COLAB, "")
    dados = cenario.get("/api/cadastros").json()
    assert dados["valor_diaria"] == "135.00" and dados["max_diarias"] == 60


# ---------------------------------------------------------------------------
# Respostas da Thais (09/10/2026)
# ---------------------------------------------------------------------------
def test_pedido_antigo_com_diaria_complementar_continua_legivel(cenario, db):
    """Pedidos de antes de 15/10 guardam diárias e complementar; o detalhe mostra."""
    sol = criar_adiantamento(cenario)
    linha = db.get(Solicitacao, sol["id"])
    linha.diarias, linha.valor_complementar = 3, Decimal("250.00")
    linha.valor_total = Decimal("655.00")
    db.commit()
    entrar(cenario, COLAB, "")
    antigo = cenario.get(f"/api/solicitacoes/{sol['id']}").json()
    assert antigo["diarias"] == 3 and antigo["valor_complementar"] == "250.00"
    assert antigo["diaria_complementar"] is True and antigo["valor_total"] == "655.00"


def test_prazo_da_prestacao_lembrete_e_vencimento(cenario, db, settings):
    from datetime import datetime

    sol = adiantamento_pago(cenario)
    prazo = FIM + timedelta(days=60)
    assert sol["prazo_prestacao"] == prazo.isoformat()

    def rodar(dia):
        return processar_expiracoes(db, settings, agora=datetime.combine(dia, datetime.min.time()))

    assert rodar(prazo - timedelta(days=8))["lembretes_prestacao"] == 0
    assert rodar(prazo - timedelta(days=7))["lembretes_prestacao"] == 1
    assert rodar(prazo)["lembretes_prestacao"] == 0  # não repete
    assert rodar(prazo)["prestacoes_vencidas"] == 0
    assert rodar(prazo + timedelta(days=1))["prestacoes_vencidas"] == 1
    assert rodar(prazo + timedelta(days=30))["prestacoes_vencidas"] == 0  # avisa uma vez
    vencida = [n for n in avisos(db, sol["id"]) if "atrasada" in n.assunto]
    assert len(vencida) == 1 and COLAB in vencida[0].para and THAIS in vencida[0].para
    # não cancela nem muda o status: o dinheiro já foi pago
    entrar(cenario, COLAB, "")
    assert cenario.get(f"/api/solicitacoes/{sol['id']}").json()["status"] == "aguardando_prestacao"


def test_prazo_nao_se_aplica_depois_da_prestacao(cenario, db, settings):
    from datetime import datetime

    sol = adiantamento_pago(cenario)
    prestar(cenario, sol["id"], [nota(arquivo=0)], [("n.jpg", JPG, "image/jpeg")])
    resultado = processar_expiracoes(db, settings, agora=datetime(2030, 1, 1))
    assert resultado["prestacoes_vencidas"] == 0 and resultado["lembretes_prestacao"] == 0


JULIANA = "juliana@tecnored.com.br"


def test_financeiro_nao_confere_o_proprio_pedido(cenario):
    entrar(cenario, JULIANA, "financeiro", "Juliana")
    # pedido da Thais (financeiro) — de alimentação
    entrar(cenario, THAIS, "financeiro", "Thais")
    completar_perfil(cenario)
    from tests.test_alimentacao import enviar

    r = enviar(cenario)
    assert r.status_code == 201, r.text
    sol = r.json()
    assert "conferir" not in sol["acoes"]
    r = decidir(cenario, sol["id"], "conferir", THAIS, "financeiro")
    assert r.status_code == 403 and "Outra pessoa do financeiro" in r.json()["detail"]
    # outra pessoa do financeiro confere
    entrar(cenario, JULIANA, "financeiro", "Juliana")
    assert "conferir" in cenario.get(f"/api/solicitacoes/{sol['id']}").json()["acoes"]
    r = decidir(cenario, sol["id"], "conferir", JULIANA, "financeiro")
    assert r.json()["status"] == "aguardando_gestor"


def test_financeiro_nao_confere_a_propria_prestacao_nem_devolucao(cenario):
    entrar(cenario, JULIANA, "financeiro", "Juliana")
    entrar(cenario, THAIS, "financeiro", "Thais")
    completar_perfil(cenario)
    r = cenario.post("/api/solicitacoes/adiantamento", json=pedido())
    sol = r.json()
    decidir(cenario, sol["id"], "aprovar", GESTOR, "gestor")
    pagar(cenario, sol["id"])  # pagar o próprio não foi vetado pela Thais
    entrar(cenario, THAIS, "financeiro")
    r = cenario.post(
        f"/api/solicitacoes/{sol['id']}/prestacao",
        data={"despesas": json.dumps([nota("refeicao", "100,00", arquivo=0)])},
        files=[("arquivos", ("n.jpg", JPG, "image/jpeg"))],
    )
    assert r.status_code == 200, r.text
    assert decidir(cenario, sol["id"], "conferir", THAIS, "financeiro").status_code == 403
    assert decidir(cenario, sol["id"], "conferir", JULIANA, "financeiro").status_code == 200
    entrar(cenario, THAIS, "financeiro")
    r = cenario.post(
        f"/api/solicitacoes/{sol['id']}/comprovante",
        data={"data_transferencia": HOJE.isoformat()},
        files={"arquivo": ("p.pdf", PDF, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    assert "confirmar_devolucao" not in r.json()["acoes"]
    r = cenario.post(f"/api/solicitacoes/{sol['id']}/confirmar-devolucao", json={"aprovar": True})
    assert r.status_code == 403
    entrar(cenario, JULIANA, "financeiro")
    r = cenario.post(f"/api/solicitacoes/{sol['id']}/confirmar-devolucao", json={"aprovar": True})
    assert r.json()["status"] == "encerrado"


def test_categorias_novas_e_descricao_em_despesas_diversas(cenario):
    sol = adiantamento_pago(cenario)
    notas = [
        nota("estacionamento_pedagio", "120,00", arquivo=0, descricao="Pedágios"),
        nota("despesas_diversas", "10,00", arquivo=1, descricao="Cópias"),
    ]
    arquivos = [("a.jpg", JPG, "image/jpeg"), ("b.jpg", JPG, "image/jpeg")]
    r = prestar(cenario, sol["id"], notas, arquivos)
    assert r.status_code == 200, r.text
    rotulos = [d["categoria_rotulo"] for d in r.json()["despesas"]]
    assert rotulos == ["Estacionamento e pedágios", "Despesas diversas"]
    # nome antigo não é mais aceito
    entrar(cenario, THAIS, "financeiro")
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro", False, "Teste")
    atual = cenario.get(f"/api/solicitacoes/{sol['id']}").json()
    r = prestar(
        cenario,
        sol["id"],
        [nota("transporte", "10,00", id=atual["despesas"][0]["id"])],
        [],
    )
    assert "categoria inválida" in r.json()["detail"]
