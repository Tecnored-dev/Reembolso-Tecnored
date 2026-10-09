"""Fluxo de alimentação: Thais confere → gestor aprova → Thais paga."""

from __future__ import annotations

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


def enviar(
    cliente, *, valor="45,90", gestor=GESTOR, arquivo=("nota.jpg", JPG, "image/jpeg"), **extra
):
    dados = {
        "data_despesa": extra.get("data_despesa", date.today().isoformat()),
        "valor": valor,
        "descricao": extra.get("descricao", "Almoço com cliente"),
        "empresa_id": extra.get("empresa_id", "1"),
    }
    if gestor:
        dados["gestor_email"] = gestor
    files = {"arquivo": arquivo} if arquivo else None
    return cliente.post("/api/solicitacoes/alimentacao", data=dados, files=files)


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


def test_devolucao_do_gestor_volta_para_conferencia(cenario):
    sol = criar(cenario)
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro")
    r = decidir(cenario, sol["id"], "aprovar", GESTOR, "gestor", aprovar=False)
    assert r.status_code == 400  # devolver exige motivo
    r = decidir(cenario, sol["id"], "aprovar", GESTOR, "gestor", False, "Nota ilegível")
    assert r.json()["status"] == "devolvido" and r.json()["motivo_devolucao"] == "Nota ilegível"

    entrar(cenario, COLAB)
    antiga = cenario.storage.raiz.rglob("*.jpg").__next__()
    r = cenario.post(
        f"/api/solicitacoes/{sol['id']}/reenviar",
        data={
            "data_despesa": date.today().isoformat(),
            "valor": "50,00",
            "descricao": "Almoço (nota nova)",
            "empresa_id": "2",
            "gestor_email": GESTOR,
        },
        files={"arquivo": ("nota.pdf", PDF, "application/pdf")},
    )
    corpo = r.json()
    assert r.status_code == 200, r.text
    assert corpo["status"] == "em_conferencia"  # volta para a Thais, não para o gestor
    assert corpo["valor_total"] == "50.00" and corpo["empresa"] == "TECNORED MARABA"
    assert corpo["motivo_devolucao"] is None
    assert corpo["despesas"][0]["arquivo_tipo"] == "application/pdf"
    assert not antiga.exists()  # arquivo velho removido do armazenamento


def test_financeiro_pode_devolver_e_reenviar_sem_trocar_arquivo(cenario):
    sol = criar(cenario)
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro", False, "Falta o CNPJ")
    entrar(cenario, COLAB)
    r = cenario.post(
        f"/api/solicitacoes/{sol['id']}/reenviar",
        data={
            "data_despesa": date.today().isoformat(),
            "valor": "45,90",
            "descricao": "Almoço",
            "empresa_id": "1",
            "gestor_email": GESTOR,
        },
    )
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
    r = cenario.post(
        f"/api/solicitacoes/{sol['id']}/reenviar",
        data={"data_despesa": "2026-10-01", "valor": "1", "descricao": "x", "empresa_id": "1"},
    )
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
    assert criar(cenario, valor="135,00")["alerta_limite"] is None
    sol = criar(cenario, valor="135,01")
    assert sol["status"] == "em_conferencia"  # só alerta, não bloqueia
    assert "135,00" in sol["alerta_limite"]


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
    assert [e["nome"] for e in dados["empresas"]] == ["TECNORED", "TECNORED MARABA"]
    perfil = cenario.get("/api/perfil").json()
    assert perfil["completo"] is True and perfil["matricula"] == "1234"
    assert (
        cenario.put("/api/perfil", json={"matricula": "1", "centro_custo_id": 99}).status_code
        == 400
    )
