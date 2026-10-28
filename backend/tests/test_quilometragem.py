"""Quilometragem com veículo próprio (Thais, 22/10): R$ 1,00 por km, sem comprovante,
só no reembolso. Versão provisória: o colaborador digita os km e informa o percurso."""

from __future__ import annotations

from datetime import date

from tests.test_alimentacao import (
    COLAB,
    JPG,
    THAIS,
    decidir,
    entrar,
    nota_despesa,
    reenviar,
)
from tests.test_alimentacao import cenario as cenario  # fixture reaproveitada
from tests.test_alimentacao import enviar as enviar_alimentacao

PERCURSO = ["Rua A, 10 - Pindamonhangaba", "Av. B, 200 - Taubaté", "Rua A, 10 - Pindamonhangaba"]


def nota_km(km="42,5", percurso=None, descricao="Visita ao cliente", id=None, **extra) -> dict:
    nota = nota_despesa("0,00", None, "quilometragem", None, id=id, descricao=descricao)
    nota["km"] = km
    nota["percurso"] = PERCURSO if percurso is None else percurso
    nota.update(extra)
    return nota


def enviar(cliente, notas, arquivos=None):
    entrar(cliente, COLAB)
    return enviar_alimentacao(cliente, notas=notas, arquivos=arquivos)


def test_quilometragem_vale_um_real_por_km_e_nao_tem_comprovante(cenario):
    r = enviar(cenario, [nota_km("42,5")])
    assert r.status_code == 201, r.text
    sol = r.json()
    assert sol["valor_total"] == "42.50"
    d = sol["despesas"][0]
    assert d["categoria_rotulo"] == "Quilometragem com veículo próprio"
    assert d["km"] == "42.5" and d["valor"] == "42.50"
    assert d["percurso"] == PERCURSO
    assert d["arquivo_nome"] is None
    r = cenario.get(f"/api/solicitacoes/{sol['id']}/despesas/{d['id']}/arquivo")
    assert r.status_code == 404


def test_quilometragem_sem_o_campo_valor_como_o_formulario_envia(cenario):
    nota = nota_km("521")
    del nota["valor"]  # o formulário não manda valor na quilometragem
    r = enviar(cenario, [nota])
    assert r.status_code == 201, r.text
    assert r.json()["valor_total"] == "521.00"


def test_nota_comum_sem_valor_continua_recusada(cenario):
    nota = nota_despesa("18,00", None, "taxi_uber", 0)
    del nota["valor"]
    r = enviar(cenario, [nota], [("arquivos", ("u.jpg", JPG, "image/jpeg"))])
    assert r.status_code == 400 and "Valor inválido" in r.text


def test_valor_enviado_pelo_cliente_e_ignorado(cenario):
    r = enviar(cenario, [nota_km("10", valor="999,00")])
    assert r.status_code == 201, r.text
    assert r.json()["valor_total"] == "10.00"


def test_mistura_com_nota_normal_e_fluxo_ate_o_pagamento(cenario):
    notas = [nota_km("20"), nota_despesa("18,00", None, "taxi_uber", 0)]
    r = enviar(cenario, notas, [("arquivos", ("u.jpg", JPG, "image/jpeg"))])
    assert r.status_code == 201, r.text
    sol = r.json()
    assert sol["valor_total"] == "38.00"
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro")
    r = decidir(cenario, sol["id"], "aprovar", "gestor@tecnored.com.br", "gestor")
    assert r.json()["status"] == "aguardando_pagamento"


def test_exige_km_percurso_e_descricao(cenario):
    casos = [
        (nota_km(""), "km"),
        (nota_km("0"), "maiores que zero"),
        (nota_km("abc"), "km"),
        (nota_km("10,55"), "1 casa"),
        (nota_km("2001"), "máximo"),
        (nota_km(percurso=[]), "origem"),
        (nota_km(percurso=["Só a origem"]), "origem"),
        (nota_km(percurso=["A", "  "]), "origem"),
        (nota_km(percurso=[f"P{i}" for i in range(9)]), "origem"),
        (nota_km(percurso=["A", "B" * 201]), "muito longo"),
        (nota_km(descricao=""), "descreva"),
    ]
    for nota, trecho in casos:
        r = enviar(cenario, [nota])
        assert r.status_code == 400, (nota, r.text)
        assert trecho in r.text.lower(), (nota, r.text)


def test_quilometragem_nao_aceita_comprovante(cenario):
    nota = nota_km()
    nota["arquivo"] = 0
    r = enviar(cenario, [nota], [("arquivos", ("a.jpg", JPG, "image/jpeg"))])
    assert r.status_code == 400 and "comprovante" in r.text


def test_km_e_percurso_so_valem_para_quilometragem(cenario):
    nota = nota_despesa("18,00", None, "taxi_uber", 0)
    nota["km"] = "10"
    arquivos = [("arquivos", ("u.jpg", JPG, "image/jpeg"))]
    r = enviar(cenario, [nota], arquivos)
    assert r.status_code == 201, r.text
    d = r.json()["despesas"][0]
    assert d["km"] is None and d["percurso"] is None and d["valor"] == "18.00"
    nota["percurso"] = PERCURSO  # percurso em outro tipo é recusado
    r = enviar(cenario, [nota], arquivos)
    assert r.status_code == 400 and "quilometragem" in r.text


def test_nao_vale_na_prestacao_do_adiantamento(cenario):
    from tests.test_adiantamento import adiantamento_pago, nota, prestar

    sol = adiantamento_pago(cenario)
    r = prestar(
        cenario,
        sol["id"],
        [nota("quilometragem", "10,00", arquivo=0, descricao="10 km")],
        [("a.jpg", JPG, "image/jpeg")],
    )
    assert r.status_code == 400 and "categoria inválida" in r.text


def test_correcao_edita_km_e_troca_de_tipo(cenario):
    sol = enviar(cenario, [nota_km("30")]).json()
    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro", False, "Km errado")
    entrar(cenario, COLAB)
    km_id = sol["despesas"][0]["id"]
    r = reenviar(cenario, sol, [nota_km("25,5", id=km_id)])
    assert r.status_code == 200, r.text
    assert r.json()["valor_total"] == "25.50" and r.json()["despesas"][0]["km"] == "25.5"

    decidir(cenario, sol["id"], "conferir", THAIS, "financeiro", False, "Troque")
    entrar(cenario, COLAB)
    # virar uma nota comum sem anexar arquivo não pode
    virou = nota_despesa("18,00", None, "taxi_uber", None, id=km_id)
    r = reenviar(cenario, sol, [virou])
    assert r.status_code == 400
    # com arquivo, pode (e perde os km)
    virou["arquivo"] = 0
    r = reenviar(cenario, sol, [virou], [("arquivos", ("u.jpg", JPG, "image/jpeg"))])
    assert r.status_code == 200, r.text
    d = r.json()["despesas"][0]
    assert d["km"] is None and d["percurso"] is None and d["arquivo_nome"] == "u.jpg"


def test_cadastros_trazem_valor_por_km(cenario):
    entrar(cenario, COLAB)
    dados = cenario.get("/api/cadastros").json()
    assert dados["valor_km"] == "1.00" and dados["km_maximo"] == "2000"
    assert dados["max_pontos_percurso"] == 8


def test_data_futura_continua_barrada(cenario):
    nota = nota_km()
    nota["data_despesa"] = date(2999, 1, 1).isoformat()
    assert enviar(cenario, [nota]).status_code == 400
