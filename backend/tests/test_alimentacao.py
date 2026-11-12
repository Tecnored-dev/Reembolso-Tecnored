"""Reembolso de despesas - alimentação: Thais confere → gestor aprova → Thais paga.

Desde 15/10 o pedido aceita várias notas, cada uma com categoria (Thais)."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import Notificacao, Solicitacao
from app.services.fluxo import processar_expiracoes

JPG = b"\xff\xd8\xff\xe0" + b"0" * 200
PDF = b"%PDF-1.4\n" + b"0" * 200

COLAB = "colab@tecnored.com.br"
GESTOR = "gestor@tecnored.com.br"
OUTRO_GESTOR = "outro.gestor@tecnored.com.br"
THAIS = "thais@tecnored.com.br"


def entrar(cliente, email: str, papeis: str = "", nome: str | None = None):
    r = cliente.get(
        "/dev/login", params={"email": email, "nome": nome or email.split("@")[0], "papeis": papeis}
    )
    assert r.status_code == 302


def completar_perfil(cliente):
    r = cliente.put("/api/perfil", json={"matricula": "1234", "centro_custo_id": 1})
    assert r.status_code == 200, r.text


def nota_despesa(
    valor="45,90", data=None, categoria="refeicao", arquivo=0, id=None, descricao=""
) -> dict:
    nota = {
        "categoria": categoria,
        "data_despesa": data or date.today().isoformat(),
        "valor": valor,
        "descricao": descricao,
    }
    if arquivo is not None:
        nota["arquivo"] = arquivo
    if id is not None:
        nota["id"] = id
    return nota


def corpo_despesas(notas: list[dict], gestor=GESTOR, **extra) -> dict:
    dados = {
        "descricao": extra.pop("descricao", "Almoço com cliente"),
        "motivo": extra.pop("motivo", "Visita técnica"),
        "empresa_id": extra.pop("empresa_id", "1"),
        "centro_custo_id": extra.pop("centro_custo_id", "1"),
        "despesas": json.dumps(notas),
        **extra,
    }
    if gestor:
        dados.setdefault("gestor_email", gestor)
    return dados


def enviar(
    cliente,
    *,
    valor="45,90",
    gestor=GESTOR,
    arquivo=("nota.jpg", JPG, "image/jpeg"),
    rota="alimentacao",
    **extra,
):
    """Um pedido com uma nota (ou as notas de `notas=[...]`)."""
    notas = extra.pop("notas", None) or [
        nota_despesa(
            valor,
            extra.pop("data_despesa", None),
            extra.pop("categoria", "refeicao"),
            0 if arquivo else None,
        )
    ]
    arquivos = extra.pop("arquivos", None) or ([("arquivos", arquivo)] if arquivo else [])
    return cliente.post(
        f"/api/solicitacoes/{rota}",
        data=corpo_despesas(notas, gestor, **extra),
        files=arquivos or None,
    )


def reenviar(cliente, sol: dict, notas: list[dict], arquivos=None, **extra):
    return cliente.post(
        f"/api/solicitacoes/{sol['id']}/reenviar",
        data=corpo_despesas(notas, **extra),
        files=arquivos or None,
    )


@pytest.fixture
def cenario(cliente):
    """Todos já entraram uma vez (é assim que o sistema conhece gestores e financeiro)."""
    entrar(cliente, GESTOR, "gestor", "Gestor")
    entrar(cliente, OUTRO_GESTOR, "gestor", "Outro Gestor")
    entrar(cliente, THAIS, "financeiro", "Thais")
    entrar(cliente, COLAB, "", "Colab")
    completar_perfil(cliente)
    return cliente


def criar(cliente, **kw) -> dict:
    entrar(cliente, COLAB, "", "Colab")
    r = enviar(cliente, **kw)
    assert r.status_code == 201, r.text
    return r.json()


def decidir(cliente, sol_id, rota, quem, papeis, aprovar=True, comentario=None):
    entrar(cliente, quem, papeis)
    return cliente.post(
        f"/api/solicitacoes/{sol_id}/{rota}", json={"aprovar": aprovar, "comentario": comentario}
    )


# ---------------------------------------------------------------------------
def test_fluxo_completo(cenario, db):
    sol = criar(cenario)
    assert sol["status"] == "em_conferencia"
    assert sol["codigo"] == f"REE-{sol['id']:06d}"
    assert sol["matricula"] == "1234" and sol["centro_custo"] == "3350 - T.I / T.A"
    assert sol["empresa"] == "TECNORED" and sol["gestor_nome"] == "Gestor"

    r = decidir(cenario, sol["id"], "conferir", THAIS, "financeiro")
    assert r.json()["status"] == "aguardando_gestor"

    r = decidir(cenario, sol["id"], "aprovar", GESTOR, "gestor")
    assert r.json()["status"] == "aguardando_pagamento"
    assert r.json()["aprovado_por"] == "gestor"

    entrar(cenario, THAIS, "financeiro")
    r = cenario.post(f"/api/solicitacoes/{sol['id']}/pagar", json={"data_pagamento": "2026-10-06"})
    final = r.json()
    assert final["status"] == "pago" and final["data_pagamento"] == "2026-10-06"
    assert [h["acao"] for h in final["historico"]] == ["enviado", "conferido", "aprovado", "pago"]

    avisos = db.scalars(select(Notificacao).order_by(Notificacao.id)).all()
    assert avisos[0].para == THAIS  # nova para conferir
    assert any(a.para == GESTOR for a in avisos)  # aguardando aprovação
    assert sum(COLAB in a.para for a in avisos) == 3  # conferida, aprovada, paga


def test_perfil_obrigatorio(cliente):
    entrar(cliente, GESTOR, "gestor")
    entrar(cliente, COLAB)
    r = enviar(cliente)
    assert r.status_code == 400 and "perfil" in r.json()["detail"]


def test_gestor_obrigatorio_e_valido(cenario):
    entrar(cenario, COLAB)
    assert enviar(cenario, gestor=None).status_code == 400
    r = enviar(cenario, gestor="ninguem@tecnored.com.br")
    assert r.status_code == 400 and "Gestor" in r.json()["detail"]


def test_lista_de_gestores_sem_o_proprio(cenario):
    entrar(cenario, GESTOR, "gestor")
    emails = [g["email"] for g in cenario.get("/api/gestores").json()]
    assert emails == [OUTRO_GESTOR]


def test_solicitante_gestor_pula_aprovacao(cenario):
    entrar(cenario, GESTOR, "gestor", "Gestor")
    completar_perfil(cenario)
    r = enviar(cenario, gestor=None)
    assert r.status_code == 201 and r.json()["pula_gestor"] is True
    r = decidir(cenario, r.json()["id"], "conferir", THAIS, "financeiro")
    assert r.json()["status"] == "aguardando_pagamento"


def test_recusa_do_gestor_finaliza(cenario, db, settings):
    """Thais, 15/10: o gestor não devolve; recusar finaliza o pedido."""
    sol = criar(cenario)
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro")
    r = decidir(cenario, sol["id"], "aprovar", GESTOR, "gestor", aprovar=False)
    assert r.status_code == 400 and "motivo da recusa" in r.json()["detail"]
    r = decidir(cenario, sol["id"], "aprovar", GESTOR, "gestor", False, "Fora da política")
    recusado = r.json()
    assert recusado["status"] == "recusado" and recusado["status_rotulo"] == "Finalizado - Recusado"
    assert recusado["recusado_por"] == "gestor" and recusado["motivo_recusa"] == "Fora da política"
    assert recusado["acoes"] == []
    assert [h["acao"] for h in recusado["historico"]][-1] == "recusado"

    # O colaborador é avisado, não pode corrigir e o pedido não volta para fila nenhuma.
    aviso = db.scalars(select(Notificacao).order_by(Notificacao.id.desc())).first()
    assert aviso.para == COLAB and "recusada" in aviso.assunto
    entrar(cenario, COLAB)
    assert cenario.get(f"/api/solicitacoes/{sol['id']}").json()["acoes"] == []
    assert decidir(cenario, sol["id"], "conferir", THAIS, "financeiro").status_code == 400
    for fila in ("conferencia", "pagamento"):
        assert cenario.get("/api/solicitacoes", params={"escopo": fila}).json() == []
    # E não expira nem é cancelado depois.
    from datetime import datetime

    resultado = processar_expiracoes(db, settings, agora=datetime(2030, 1, 1))
    assert resultado["cancelamentos"] == 0


def test_reenvio_depois_da_devolucao_do_financeiro_troca_o_arquivo(cenario):
    sol = criar(cenario)
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro", False, "Nota ilegível")

    entrar(cenario, COLAB)
    antiga = cenario.storage.raiz.rglob("*.jpg").__next__()
    nota = nota_despesa("50,00", arquivo=0, id=sol["despesas"][0]["id"])
    r = reenviar(
        cenario,
        sol,
        [nota],
        [("arquivos", ("nota.pdf", PDF, "application/pdf"))],
        descricao="Almoço (nota nova)",
    )
    corpo = r.json()
    assert r.status_code == 200, r.text
    assert corpo["status"] == "em_conferencia"  # volta para a Thais, não para o gestor
    assert corpo["valor_total"] == "50.00" and corpo["empresa"] == "TECNORED"
    assert corpo["motivo_devolucao"] is None
    assert corpo["despesas"][0]["arquivo_tipo"] == "application/pdf"
    assert not antiga.exists()  # arquivo velho removido do armazenamento


def test_financeiro_pode_devolver_e_reenviar_sem_trocar_arquivo(cenario):
    sol = criar(cenario)
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro", False, "Falta o CNPJ")
    entrar(cenario, COLAB)
    r = reenviar(cenario, sol, [nota_despesa(arquivo=None, id=sol["despesas"][0]["id"])])
    assert r.json()["status"] == "em_conferencia"
    assert r.json()["despesas"][0]["arquivo_tipo"] == "image/jpeg"


def test_permissoes(cenario):
    sol = criar(cenario)
    # colaborador não confere
    assert decidir(cenario, sol["id"], "conferir", COLAB, "").status_code == 403
    # gestor não aprova antes da conferência
    r = decidir(cenario, sol["id"], "aprovar", GESTOR, "gestor")
    assert r.status_code == 400
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro")
    # outro gestor nem enxerga
    assert decidir(cenario, sol["id"], "aprovar", OUTRO_GESTOR, "gestor").status_code == 404
    # outro colaborador nem enxerga
    entrar(cenario, "intruso@tecnored.com.br")
    assert cenario.get(f"/api/solicitacoes/{sol['id']}").status_code == 404
    # colaborador não reenvia o que não está devolvido
    entrar(cenario, COLAB)
    r = reenviar(cenario, sol, [nota_despesa(arquivo=None, id=sol["despesas"][0]["id"])])
    assert r.status_code == 400


def test_pagar_so_depois_de_aprovado(cenario):
    sol = criar(cenario)
    entrar(cenario, THAIS, "financeiro")
    r = cenario.post(f"/api/solicitacoes/{sol['id']}/pagar", json={"data_pagamento": "2026-10-06"})
    assert r.status_code == 400


def test_validacoes_de_arquivo(cenario):
    entrar(cenario, COLAB)
    assert enviar(cenario, arquivo=None).status_code == 400
    r = enviar(cenario, arquivo=("nota.jpg", b"texto qualquer", "image/jpeg"))
    assert r.status_code == 400 and "Formato" in r.json()["detail"]
    assert cenario.storage.raiz.exists() is False or not list(cenario.storage.raiz.rglob("*.*"))


def test_validacoes_de_valor_e_data(cenario):
    entrar(cenario, COLAB)
    amanha = (date.today() + timedelta(days=1)).isoformat()
    assert enviar(cenario, data_despesa=amanha).status_code == 400
    assert enviar(cenario, valor="0").status_code == 400
    assert enviar(cenario, valor="abc").status_code == 400
    assert enviar(cenario, valor="10,999").status_code == 400
    r = enviar(cenario, valor="1.234,56")
    assert r.status_code == 201 and r.json()["valor_total"] == "1234.56"


def test_alerta_acima_do_limite(cenario):
    """Thais, 15/10: alimentação até R$ 40 por dia (só alerta)."""
    assert criar(cenario, valor="40,00")["alerta_limite"] is None
    sol = criar(cenario, valor="40,01")
    assert sol["status"] == "em_conferencia"  # só alerta, não bloqueia
    assert "R$ 40,00 por dia" in sol["alerta_limite"]


def test_anexo_so_para_quem_ve(cenario):
    sol = criar(cenario)
    url = f"/api/solicitacoes/{sol['id']}/despesas/{sol['despesas'][0]['id']}/arquivo"
    r = cenario.get(url)
    assert r.status_code == 200 and r.content == JPG
    assert r.headers["content-type"] == "image/jpeg"
    entrar(cenario, THAIS, "financeiro")
    assert cenario.get(url).status_code == 200
    entrar(cenario, OUTRO_GESTOR, "gestor")
    assert cenario.get(url).status_code == 404


def test_escopos(cenario):
    sol = criar(cenario)
    assert [s["id"] for s in cenario.get("/api/solicitacoes?escopo=minhas").json()] == [sol["id"]]
    assert cenario.get("/api/solicitacoes?escopo=conferencia").status_code == 403

    entrar(cenario, THAIS, "financeiro")
    assert len(cenario.get("/api/solicitacoes?escopo=conferencia").json()) == 1
    detalhe = cenario.get(f"/api/solicitacoes/{sol['id']}").json()
    assert detalhe["acoes"] == ["conferir", "devolver"]
    cenario.post(f"/api/solicitacoes/{sol['id']}/conferir", json={"aprovar": True})

    entrar(cenario, GESTOR, "gestor")
    assert len(cenario.get("/api/solicitacoes?escopo=aprovacao").json()) == 1
    entrar(cenario, OUTRO_GESTOR, "gestor")
    assert cenario.get("/api/solicitacoes?escopo=aprovacao").json() == []


def test_expiracao_lembrete_e_cancelamento(cenario, db, settings):
    sol = criar(cenario)
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro", False, "Falta nota")
    registro = db.get(Solicitacao, sol["id"])
    devolvida_em = registro.ultima_movimentacao_em

    resultado = processar_expiracoes(db, settings, devolvida_em + timedelta(days=12))
    assert resultado["lembretes"] == 0 and resultado["cancelamentos"] == 0
    assert processar_expiracoes(db, settings, devolvida_em + timedelta(days=13))["lembretes"] == 1
    # idempotente: não lembra de novo
    assert processar_expiracoes(db, settings, devolvida_em + timedelta(days=14))["lembretes"] == 0
    assert (
        processar_expiracoes(db, settings, devolvida_em + timedelta(days=15))["cancelamentos"] == 1
    )
    db.refresh(registro)
    assert registro.status == "cancelado"
    assert registro.historico[-1].usuario_nome == "Sistema"


def test_tarefa_de_expiracao_so_admin(cenario):
    entrar(cenario, COLAB)
    assert cenario.post("/api/tarefas/expiracao").status_code == 403
    entrar(cenario, "admin@tecnored.com.br", "admin")
    assert cenario.post("/api/tarefas/expiracao").json() == {
        "lembretes": 0,
        "cancelamentos": 0,
        "lembretes_prestacao": 0,
        "prestacoes_vencidas": 0,
    }


def test_cadastros_e_perfil(cenario):
    dados = cenario.get("/api/cadastros").json()
    assert dados["centros_custo"][0]["rotulo"] == "3350 - T.I / T.A"
    # "Inicialmente só Tecnored" (13/10): a Marabá está inativa.
    assert [e["nome"] for e in dados["empresas"]] == ["TECNORED"]
    perfil = cenario.get("/api/perfil").json()
    assert perfil["completo"] is True and perfil["matricula"] == "1234"
    assert (
        cenario.put("/api/perfil", json={"matricula": "1", "centro_custo_id": 99}).status_code
        == 400
    )


def test_empresa_inativa_nao_aceita(cenario):
    entrar(cenario, COLAB)
    r = enviar(cenario, empresa_id="2")  # TECNORED MARABA, inativa desde 13/10
    assert r.status_code == 400 and "Empresa de débito inválida" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Motivo (lista do ARGO) e reembolso de despesas com várias notas (Thais, 15/10)
# ---------------------------------------------------------------------------
def test_motivo_obrigatorio_e_da_lista(cenario):
    entrar(cenario, COLAB)
    assert "Escolha o motivo" in enviar(cenario, motivo="").json()["detail"]
    assert "Escolha o motivo" in enviar(cenario, motivo="Churrasco").json()["detail"]
    sol = enviar(cenario, motivo="Reunião comercial").json()
    assert sol["motivo"] == "Reunião comercial"
    assert sol["local_refeicao"] is None  # "Onde foi a refeição?" saiu


def test_varias_notas_com_categoria(cenario):
    entrar(cenario, COLAB)
    ontem = (date.today() - timedelta(days=1)).isoformat()
    anteontem = (date.today() - timedelta(days=2)).isoformat()
    notas = [
        nota_despesa("30,00", ontem, "refeicao", 0),
        nota_despesa("25,00", anteontem, "refeicao", 1),
        nota_despesa("38,00", None, "almoco_pinda", 2),
    ]
    arquivos = [
        ("arquivos", ("a.jpg", JPG, "image/jpeg")),
        ("arquivos", ("b.pdf", PDF, "application/pdf")),
        ("arquivos", ("c.jpg", JPG, "image/jpeg")),
    ]
    r = enviar(cenario, notas=notas, arquivos=arquivos)
    assert r.status_code == 201, r.text
    sol = r.json()
    assert sol["valor_total"] == "93.00" and len(sol["despesas"]) == 3
    assert [d["categoria_rotulo"] for d in sol["despesas"]] == [
        "Refeição - Nacional",
        "Refeição - Nacional",
        "Almoço em Pinda - Fora da planta",
    ]
    assert sol["valor_total"] == "93.00"
    assert sol["alerta_limite"] is None  # refeição de cada dia ≤ R$ 40


def test_limite_de_r40_soma_as_refeicoes_do_dia(cenario):
    entrar(cenario, COLAB)
    notas = [
        nota_despesa("25,00", None, "refeicao", 0),
        nota_despesa("20,00", None, "almoco_pinda", 1),
    ]
    arquivos = [
        ("arquivos", ("a.jpg", JPG, "image/jpeg")),
        ("arquivos", ("b.jpg", JPG, "image/jpeg")),
    ]
    sol = enviar(cenario, notas=notas, arquivos=arquivos).json()
    assert "R$ 40,00 por dia" in sol["alerta_limite"]
    # Hospedagem é de "Despesas diversas": na alimentação a categoria é recusada.
    r = enviar(cenario, valor="400,00", categoria="hospedagem")
    assert r.status_code == 400 and "categoria inválida" in r.json()["detail"]


def test_categoria_obrigatoria_e_da_lista(cenario):
    entrar(cenario, COLAB)
    # Na alimentação só vale refeição e almoço em Pinda (o resto é de despesas diversas).
    for categoria in ("", "churrasco", "diversos", "taxi_uber", "quilometragem"):
        r = enviar(cenario, categoria=categoria)
        assert r.status_code == 400 and "categoria inválida" in r.json()["detail"]


def test_nota_sem_arquivo_e_recusada(cenario):
    entrar(cenario, COLAB)
    r = enviar(cenario, arquivo=None)
    assert r.status_code == 400 and "anexe a foto" in r.json()["detail"]


def test_correcao_adiciona_e_remove_notas(cenario):
    sol = criar(cenario)
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro", False, "Faltou o Uber")
    entrar(cenario, COLAB)
    notas = [
        nota_despesa("45,90", arquivo=None, id=sol["despesas"][0]["id"]),
        nota_despesa("18,00", None, "almoco_pinda", 0),
    ]
    r = reenviar(cenario, sol, notas, [("arquivos", ("u.jpg", JPG, "image/jpeg"))])
    assert r.status_code == 200, r.text
    assert r.json()["valor_total"] == "63.90" and len(r.json()["despesas"]) == 2
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro", False, "Só o Uber")
    entrar(cenario, COLAB)
    uber = r.json()["despesas"][1]["id"]
    r = reenviar(cenario, sol, [nota_despesa("18,00", None, "almoco_pinda", None, id=uber)])
    assert r.json()["valor_total"] == "18.00" and len(r.json()["despesas"]) == 1


def test_pedido_antigo_de_uma_nota_ainda_pode_ser_corrigido(cenario, db):
    """Pedidos de antes de 15/10 tinham o local da refeição: a correção limpa."""
    sol = criar(cenario)
    registro = db.get(Solicitacao, sol["id"])
    registro.local_refeicao = "pinda"
    db.commit()
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro", False, "Corrigir")
    entrar(cenario, COLAB)
    r = reenviar(cenario, sol, [nota_despesa(arquivo=None, id=sol["despesas"][0]["id"])])
    assert r.status_code == 200 and r.json()["local_refeicao"] is None


def test_cadastros_trazem_motivos_e_limite(cenario):
    dados = cenario.get("/api/cadastros").json()
    assert dados["motivos"][0] == "Despesas cartório" and "Visita técnica" in dados["motivos"]
    assert dados["limite_alimentacao_dia"] == "40.00"
    assert "locais_refeicao" not in dados


def test_anexo_com_nome_acentuado_e_emoji_baixa(cenario):
    """Nome fora do latin-1 ia cru no Content-Disposition e o download dava 500."""
    nome = "Almoço – café ☕.jpg"  # noqa: RUF001 (o travessão quebrava o download)
    sol = enviar(cenario, arquivo=(nome, JPG, "image/jpeg")).json()
    url = f"/api/solicitacoes/{sol['id']}/despesas/{sol['despesas'][0]['id']}/arquivo"
    r = cenario.get(url)
    assert r.status_code == 200 and r.content == JPG
    disp = r.headers["content-disposition"]
    assert "filename*=UTF-8''Almo%C3%A7o%20%E2%80%93%20caf%C3%A9%20%E2%98%95.jpg" in disp


def test_arquivos_demais_sao_recusados_antes_de_ler(cenario):
    arquivos = [("arquivos", (f"n{i}.jpg", JPG, "image/jpeg")) for i in range(31)]
    r = enviar(cenario, arquivos=arquivos)
    assert r.status_code == 400 and "Máximo de 30 arquivos" in r.json()["detail"]
