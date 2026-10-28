"""OCR, etapa 1: interpretação do texto já extraído do comprovante.

Textos fictícios (nenhuma nota real: LGPD). Os CNPJs são exemplos com dígito
verificador válido; a chave de acesso foi montada com eles.
"""

from __future__ import annotations

import time
from datetime import date

from app.config import CATEGORIAS_VIAGEM
from app.ocr.interpretacao import (
    _PADROES_CATEGORIA,
    AMBIGUO,
    IDENTIFICADO,
    ILEGIVEL,
    LIDO,
    NAO_IDENTIFICADO,
    PARCIAL,
    Campo,
    cnpj_valido,
    interpretar,
)

HOJE = date(2026, 10, 20)
CHAVE = "3526 1011 2223 3300 0181 6500 1000 0123 4511 2345 6787"

NFCE = f"""
RESTAURANTE SABOR DO VALE LTDA
CNPJ: 11.222.333/0001-81 IE: 123456789
Rua das Flores, 100 - Centro - Pindamonhangaba/SP
Documento Auxiliar da Nota Fiscal de Consumidor Eletrônica
COD DESCRIÇÃO QTD UN VL UNIT VL TOTAL
001 PRATO EXECUTIVO 2 UN 26,00 52,00
Qtde. total de itens 2
Valor total R$ 52,00
Desconto R$ 3,10
Valor a Pagar R$ 48,90
FORMA PAGAMENTO VALOR PAGO
Dinheiro 50,00
Troco R$ 1,10
NFC-e nº 000012345 Série 001 Emissão 18/10/2026 12:41:07
Consulte pela Chave de Acesso em www.nfce.fazenda.sp.gov.br
{CHAVE}
CONSUMIDOR CPF: 123.456.789-09
Protocolo de autorização: 135260000000001 19/10/2026 12:41:30
Tributos Totais Incidentes (Lei Federal 12.741/2012) R$ 5,20
"""

# Cabeçalho neutro para testar um campo de cada vez (texto suficiente para não ser ilegível).
CABECALHO = "Comercial Exemplo Ltda\nObrigado pela preferencia\n"


def ler(texto: str):
    return interpretar(texto, hoje=HOJE)


# ---------------------------------------------------------------------------
# Comprovante completo
# ---------------------------------------------------------------------------
def test_nfce_completa():
    leitura = ler(NFCE)
    assert leitura.status == LIDO
    assert leitura.data == Campo("2026-10-18", IDENTIFICADO)
    # Com desconto, dinheiro e troco: vale o "Valor a pagar".
    assert leitura.valor_total == Campo("48.90", IDENTIFICADO)
    assert leitura.cnpj == Campo("11222333000181", IDENTIFICADO)
    assert leitura.numero_documento == Campo("12345", IDENTIFICADO)
    assert leitura.estabelecimento == Campo("RESTAURANTE SABOR DO VALE LTDA", IDENTIFICADO)
    assert leitura.categoria_sugerida == Campo("refeicao", IDENTIFICADO)
    assert leitura.avisos == ()


def test_cupom_sat_com_dois_totais_diferentes_fica_ambiguo():
    leitura = ler(
        "AUTO POSTO ESTRELA LTDA\n"
        "CNPJ 11.444.777/0001-61\n"
        "EXTRATO No 004321 CUPOM FISCAL ELETRONICO - SAT\n"
        "GASOLINA COMUM 30,000 L\n"
        "TOTAL R$ 150,00\n"
        "TOTAL R$ 180,00\n"
        "20/10/2026 08:15\n"
    )
    assert leitura.status == PARCIAL
    assert leitura.valor_total == Campo("180.00", AMBIGUO, ("150.00",))
    assert leitura.numero_documento == Campo("4321", IDENTIFICADO)
    assert leitura.estabelecimento == Campo("AUTO POSTO ESTRELA LTDA", IDENTIFICADO)
    assert leitura.categoria_sugerida == Campo("combustivel", IDENTIFICADO)
    assert leitura.data == Campo("2026-10-20", IDENTIFICADO)


def test_sem_cnpj_e_sem_total():
    leitura = ler("Lanchonete da Praça\nPão de queijo 6,50\nCafé 4,00\n19/10/2026\n")
    assert leitura.cnpj == Campo()
    # Sem a palavra "total": o maior valor, para conferir.
    assert leitura.valor_total == Campo("6.50", AMBIGUO)
    assert "Não achamos o total na nota. Confira o valor." in leitura.avisos
    # Sem CNPJ, o nome é só um palpite (primeira linha).
    assert leitura.estabelecimento == Campo("Lanchonete da Praça", AMBIGUO)
    assert leitura.categoria_sugerida.valor == "refeicao"
    assert leitura.status == PARCIAL


# ---------------------------------------------------------------------------
# CNPJ e chave de acesso
# ---------------------------------------------------------------------------
def test_cnpj_valido():
    assert cnpj_valido("11222333000181")
    assert cnpj_valido("11444777000161")
    assert cnpj_valido("12ABC34501DE35")  # alfanumérico (exemplo da Receita)
    assert not cnpj_valido("11222333000182")
    assert not cnpj_valido("00000000000000")
    assert not cnpj_valido("1122233300018")
    assert not cnpj_valido("12ABC34501DEAB")


def test_cnpj_com_digito_errado_nao_e_sugerido():
    leitura = ler(CABECALHO + "CNPJ: 11.222.333/0001-82\nTOTAL 10,00\n")
    assert leitura.cnpj == Campo()
    assert "O CNPJ lido na nota não confere. Confira no comprovante." in leitura.avisos


def test_cnpj_sem_pontuacao_e_alfanumerico():
    assert ler(CABECALHO + "CNPJ 11222333000181\n").cnpj == Campo("11222333000181", IDENTIFICADO)
    alfanumerico = ler(CABECALHO + "CNPJ: 12.ABC.345/01DE-35\n").cnpj
    assert alfanumerico == Campo("12ABC34501DE35", IDENTIFICADO)


def test_cnpj_do_consumidor_e_ignorado():
    leitura = ler(CABECALHO + "TOTAL 10,00\nCONSUMIDOR CNPJ: 11.222.333/0001-81\n")
    assert leitura.cnpj == Campo()
    assert leitura.avisos == ()


def test_dois_cnpjs_ficam_ambiguos():
    leitura = ler(CABECALHO + "CNPJ 11.222.333/0001-81\nCNPJ 11.444.777/0001-61\n")
    assert leitura.cnpj == Campo("11222333000181", AMBIGUO, ("11444777000161",))


def test_chave_de_acesso_vale_mais_que_o_texto():
    # O CNPJ e o número saem da chave, mesmo com outro CNPJ lido no texto.
    leitura = ler(CABECALHO + "CNPJ 11.444.777/0001-61\nNo 999\n" + CHAVE + "\n")
    assert leitura.cnpj == Campo("11222333000181", IDENTIFICADO)
    assert leitura.numero_documento == Campo("12345", IDENTIFICADO)


def test_chave_com_digito_errado_e_ignorada():
    leitura = ler(CABECALHO + "TOTAL 10,00\n" + CHAVE[:-1] + "8\n")
    assert leitura.cnpj == Campo()
    assert leitura.numero_documento == Campo()


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def test_data_ambigua():
    leitura = ler(CABECALHO + "Data 10/10/2026\nEntrega 15/10/2026\n")
    assert leitura.data == Campo("2026-10-10", AMBIGUO, ("2026-10-15",))


def test_data_de_emissao_tem_preferencia_e_vencimento_e_ignorado():
    leitura = ler(
        CABECALHO + "Vencimento 30/10/2026\nData de emissão: 12/10/2026\nPedido 11/10/2026\n"
    )
    assert leitura.data == Campo("2026-10-12", IDENTIFICADO)


def test_data_no_futuro_pede_conferencia():
    leitura = ler(CABECALHO + "Emissão 25/12/2026\n")
    assert leitura.data == Campo("2026-12-25", AMBIGUO)
    assert "A data lida está no futuro. Confira a data da nota." in leitura.avisos


def test_formatos_de_data():
    assert ler(CABECALHO + "18/10/26 12:00\n").data.valor == "2026-10-18"
    assert ler(CABECALHO + "18.10.2026\n").data.valor == "2026-10-18"
    assert ler(CABECALHO + "2026-10-18T12:00\n").data.valor == "2026-10-18"
    assert ler(CABECALHO + "31/02/2026\n").data == Campo()  # não existe
    assert ler(CABECALHO + "18/10/1999\n").data == Campo()  # ano fora do esperado


# ---------------------------------------------------------------------------
# Valor
# ---------------------------------------------------------------------------
def test_formatos_de_valor():
    assert ler(CABECALHO + "TOTAL R$ 1.234,56\n").valor_total.valor == "1234.56"
    assert ler(CABECALHO + "TOTAL 48.90\n").valor_total.valor == "48.90"
    assert ler(CABECALHO + "TOTAL R$ 48, 90\n").valor_total.valor == "48.90"
    # Acima do máximo aceito pelo sistema: não sugere.
    assert ler(CABECALHO + "TOTAL R$ 150.000,00\n").valor_total == Campo()


def test_valor_na_linha_seguinte_ao_rotulo():
    leitura = ler(CABECALHO + "VALOR TOTAL R$\n52,00\n")
    assert leitura.valor_total == Campo("52.00", IDENTIFICADO)


def test_subtotal_troco_e_taxa_nao_sao_o_total():
    leitura = ler(
        CABECALHO
        + "SUBTOTAL 40,00\nTAXA DE SERVICO 10% 4,00\nTOTAL 44,00\nDINHEIRO 50,00\nTROCO 6,00\n"
    )
    assert leitura.valor_total == Campo("44.00", IDENTIFICADO)


# ---------------------------------------------------------------------------
# Número e estabelecimento
# ---------------------------------------------------------------------------
def test_numero_do_documento():
    assert ler(CABECALHO + "COO: 001234\n").numero_documento == Campo("1234", IDENTIFICADO)
    # NFS-e: número longo (ano + sequência).
    assert ler(CABECALHO + "NFS-e Número: 2026000042\n").numero_documento.valor == "2026000042"
    assert ler(CABECALHO + "NFS-e Numero: 42\n").numero_documento == Campo("42", IDENTIFICADO)
    # Número do endereço não é número da nota.
    assert ler(CABECALHO + "Rua das Flores, Nº 1500\n").numero_documento == Campo()


def test_estabelecimento_por_rotulo_e_na_linha_do_cnpj():
    leitura = ler("Razão social: Hotel Boa Viagem Ltda\nCNPJ 11.222.333/0001-81\nTOTAL 10,00\n")
    assert leitura.estabelecimento == Campo("Hotel Boa Viagem Ltda", IDENTIFICADO)
    leitura = ler("Obrigado e volte sempre\nPADARIA PÃO QUENTE CNPJ 11.222.333/0001-81\n")
    assert leitura.estabelecimento == Campo("PADARIA PÃO QUENTE", IDENTIFICADO)


# ---------------------------------------------------------------------------
# Categoria
# ---------------------------------------------------------------------------
def test_categorias():
    assert ler(CABECALHO + "Hotel Central\nTOTAL 10,00\n").categoria_sugerida == Campo(
        "hospedagem", IDENTIFICADO
    )
    assert ler(CABECALHO + "Estacionamento Centro\nTOTAL 10,00\n").categoria_sugerida == Campo(
        "estacionamento_pedagio", IDENTIFICADO
    )
    # Restaurante dentro do hotel: empate, o colaborador escolhe.
    empate = ler(CABECALHO + "Hotel Central - Restaurante\nTOTAL 10,00\n").categoria_sugerida
    assert empate.estado == AMBIGUO
    assert {empate.valor, *empate.alternativas} == {"hospedagem", "refeicao"}
    assert ler(CABECALHO + "TOTAL 10,00\n").categoria_sugerida == Campo()
    # "IMPOSTO" não é "POSTO".
    assert ler(CABECALHO + "IMPOSTO 1,00\nTOTAL 10,00\n").categoria_sugerida == Campo()


def test_categorias_sugeridas_existem_no_sistema():
    assert _PADROES_CATEGORIA
    assert set(_PADROES_CATEGORIA) <= set(CATEGORIAS_VIAGEM)
    # Estas dependem de contexto que a nota não mostra: nunca são sugeridas.
    assert not {"refeicao_internacional", "almoco_pinda", "despesas_diversas"} & set(
        _PADROES_CATEGORIA
    )


# ---------------------------------------------------------------------------
# Texto ruim
# ---------------------------------------------------------------------------
def test_texto_vazio_ou_ruido_e_ilegivel():
    for texto in ("", "   \n\n", "@@ ## !! 12", "lorem ipsum dolor sit amet consectetur"):
        leitura = ler(texto)
        assert leitura.status == ILEGIVEL
        assert leitura.valor_total.estado == NAO_IDENTIFICADO
        assert leitura.avisos == ("Não conseguimos ler o comprovante. Preencha os dados à mão.",)


def test_ocr_ruim_aproveita_o_que_der():
    # Letras trocadas pelo OCR: só o total sobra legível.
    leitura = ler("R3STAUR4NT3 S4B0R D0 V4L3\nCNPJ 1l.222.333/OOO1-8l\nT0TAL\nTOTAL 48,90\n")
    assert leitura.valor_total == Campo("48.90", IDENTIFICADO)
    assert leitura.cnpj == Campo()
    assert leitura.status == PARCIAL


def test_texto_enorme_e_truncado_sem_travar():
    inicio = time.monotonic()
    leitura = ler(CABECALHO + "TOTAL 10,00\n" + "9" * 500_000 + "\n" + "a1/" * 300_000)
    assert time.monotonic() - inicio < 2
    assert leitura.valor_total.valor == "10.00"
