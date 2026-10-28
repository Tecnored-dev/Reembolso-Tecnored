"""Interpretação do texto de um comprovante: texto → sugestões para o formulário.

Recebe o texto já extraído (camada de texto do PDF ou resultado do OCR) e
procura data, valor total, estabelecimento, CNPJ, número do documento e uma
categoria. São só SUGESTÕES: o colaborador confere e corrige antes de enviar.

Sem índice de confiança inventado: cada campo sai "identificado", "ambiguo"
(mais de um candidato, ou algo a conferir) ou "nao_identificado".
Funções puras e sem log: o texto da nota tem dados pessoais (LGPD).
"""

from __future__ import annotations

import itertools
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from app.config import CATEGORIAS_VIAGEM
from app.services.formatos import VALOR_MAXIMO

IDENTIFICADO = "identificado"
AMBIGUO = "ambiguo"
NAO_IDENTIFICADO = "nao_identificado"

LIDO = "lido"  # data e valor identificados
PARCIAL = "parcial"
ILEGIVEL = "ilegivel"  # nada aproveitável

MAX_TEXTO = 20_000  # caracteres analisados; o resto é ignorado
MIN_CARACTERES = 20  # letras e números; menos que isso é ilegível
MAX_NOME = 120


@dataclass(frozen=True)
class Campo:
    valor: str | None = None
    estado: str = NAO_IDENTIFICADO
    alternativas: tuple[str, ...] = ()


@dataclass(frozen=True)
class Leitura:
    status: str
    data: Campo  # "AAAA-MM-DD"
    valor_total: Campo  # "48.90"
    estabelecimento: Campo
    cnpj: Campo  # só os 14 caracteres, sem pontuação
    numero_documento: Campo
    categoria_sugerida: Campo  # chave de CATEGORIAS_VIAGEM
    avisos: tuple[str, ...] = ()


def interpretar(texto: str, hoje: date | None = None) -> Leitura:
    hoje = hoje or date.today()
    originais = [linha.strip() for linha in (texto or "")[:MAX_TEXTO].splitlines()]
    originais = [linha for linha in originais if linha]
    linhas = [_normalizar(linha) for linha in originais]

    vazio = Campo()
    if sum(c.isalnum() for c in "".join(linhas)) < MIN_CARACTERES:
        return _ilegivel()

    avisos: list[str] = []
    chave = _chave_acesso(linhas)
    cnpj, linha_cnpj = _cnpj(linhas, chave, avisos)
    campos = {
        "data": _data(linhas, hoje, avisos),
        "valor_total": _valor_total(linhas, avisos),
        "estabelecimento": _estabelecimento(originais, linhas, linha_cnpj),
        "cnpj": cnpj,
        "numero_documento": _numero(linhas, chave),
        "categoria_sugerida": _categoria(linhas),
    }
    # Só um palpite de nome ou de categoria não ajuda: sem dado da nota, é ilegível.
    if all(campos[c] == vazio for c in ("data", "valor_total", "cnpj", "numero_documento")):
        return _ilegivel()
    lido = campos["data"].estado == campos["valor_total"].estado == IDENTIFICADO
    return Leitura(status=LIDO if lido else PARCIAL, **campos, avisos=tuple(avisos))


def _ilegivel() -> Leitura:
    vazio = Campo()
    return Leitura(
        ILEGIVEL,
        vazio,
        vazio,
        vazio,
        vazio,
        vazio,
        vazio,
        ("Não conseguimos ler o comprovante. Preencha os dados à mão.",),
    )


def _normalizar(texto: str) -> str:
    """Maiúsculas e sem acento ("Emissão" → "EMISSAO"; "Nº" → "NO")."""
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).upper()


def _campo(candidatos: list[str]) -> Campo:
    """Um candidato: identificado. Vários: ambíguo, com os outros como alternativas."""
    distintos = list(dict.fromkeys(candidatos))
    if not distintos:
        return Campo()
    estado = IDENTIFICADO if len(distintos) == 1 else AMBIGUO
    return Campo(distintos[0], estado, tuple(distintos[1:]))


# ---------------------------------------------------------------------------
# CNPJ e chave de acesso da NF-e / NFC-e
# ---------------------------------------------------------------------------
_PESOS_CNPJ = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_CNPJ_FORMATADO = re.compile(
    r"(?<![0-9A-Z])([0-9A-Z]{2})\.?\s?([0-9A-Z]{3})\.?\s?([0-9A-Z]{3})\s?/\s?"
    r"([0-9A-Z]{4})\s?-\s?(\d{2})(?!\d)"
)
_CNPJ_NUMEROS = re.compile(r"(?<!\d)\d{14}(?!\d)")
# Linhas sobre quem comprou, não sobre quem vendeu.
_LINHA_CONSUMIDOR = re.compile(r"CONSUMIDOR|DESTINATARIO|TOMADOR")
_CHAVE = re.compile(r"(?<!\d)((?:\d{4}\s?){10}\d{4})(?!\d)")


def cnpj_valido(cnpj: str) -> bool:
    """Confere os dígitos verificadores. Aceita o CNPJ alfanumérico (desde
    julho/2026): letras nas 12 primeiras posições valem o código ASCII menos 48."""
    if not re.fullmatch(r"[0-9A-Z]{12}\d{2}", cnpj) or len(set(cnpj)) == 1:
        return False
    valores = [ord(c) - 48 for c in cnpj]
    for tamanho in (12, 13):
        pesos = _PESOS_CNPJ[-tamanho:]
        soma = sum(v * p for v, p in zip(valores[:tamanho], pesos, strict=True))
        resto = soma % 11
        if valores[tamanho] != (0 if resto < 2 else 11 - resto):
            return False
    return True


def _chave_valida(chave: str) -> bool:
    """Dígito verificador (módulo 11) da chave de 44 dígitos."""
    pesos = itertools.cycle(range(2, 10))
    soma = sum(int(d) * p for d, p in zip(reversed(chave[:43]), pesos, strict=False))
    resto = soma % 11
    return int(chave[43]) == (0 if resto < 2 else 11 - resto)


def _chave_acesso(linhas: list[str]) -> str | None:
    """Chave da NF-e/NFC-e: traz o CNPJ do emitente e o número sem depender do OCR
    do resto da nota (posições 7-20 e 26-34)."""
    for linha in linhas:
        for achado in _CHAVE.finditer(linha):
            chave = re.sub(r"\s", "", achado.group(1))
            if _chave_valida(chave) and cnpj_valido(chave[6:20]):
                return chave
    return None


def _cnpj(linhas: list[str], chave: str | None, avisos: list[str]) -> tuple[Campo, int | None]:
    """Devolve o campo e a linha onde o CNPJ do emitente apareceu (ajuda a achar o nome)."""
    validos: list[tuple[str, int]] = []
    invalidos = 0
    for i, linha in enumerate(linhas):
        if _LINHA_CONSUMIDOR.search(linha):
            continue
        achados = ["".join(m.groups()) for m in _CNPJ_FORMATADO.finditer(linha)]
        achados += [m.group(0) for m in _CNPJ_NUMEROS.finditer(linha)]
        for cnpj in achados:
            if cnpj_valido(cnpj):
                validos.append((cnpj, i))
            else:
                invalidos += 1

    if chave:
        emitente = chave[6:20]
        linha = next((i for cnpj, i in validos if cnpj == emitente), None)
        return Campo(emitente, IDENTIFICADO), linha
    if not validos:
        if invalidos:
            avisos.append("O CNPJ lido na nota não confere. Confira no comprovante.")
        return Campo(), None
    return _campo([cnpj for cnpj, _ in validos]), validos[0][1]


# ---------------------------------------------------------------------------
# Data de emissão
# ---------------------------------------------------------------------------
_DATA = re.compile(r"(?<![\d/])(\d{2})[/.-](\d{2})[/.-](\d{4}|\d{2})(?![\d/])")
_DATA_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_LINHA_EMISSAO = re.compile(r"EMISSAO|EMITID")
_LINHA_OUTRA_DATA = re.compile(r"VENCIMENTO|VALIDADE|VALIDO ATE|NASCIMENTO")


def _datas_da_linha(linha: str, hoje: date) -> list[date]:
    encontradas = [(d, m, a) for d, m, a in _DATA.findall(linha)]
    encontradas += [(d, m, a) for a, m, d in _DATA_ISO.findall(linha)]
    datas = []
    for dia, mes, ano in encontradas:
        ano_int = int(ano) + (2000 if len(ano) == 2 else 0)
        if not 2000 <= ano_int <= hoje.year + 1:
            continue
        try:
            datas.append(date(ano_int, int(mes), int(dia)))
        except ValueError:
            continue
    return datas


def _data(linhas: list[str], hoje: date, avisos: list[str]) -> Campo:
    emissao: list[str] = []
    outras: list[str] = []
    for linha in linhas:
        if _LINHA_OUTRA_DATA.search(linha):
            continue
        destino = emissao if _LINHA_EMISSAO.search(linha) else outras
        destino.extend(d.isoformat() for d in _datas_da_linha(linha, hoje))

    campo = _campo(emissao or outras)
    if campo.valor and date.fromisoformat(campo.valor) > hoje:
        avisos.append("A data lida está no futuro. Confira a data da nota.")
        return Campo(campo.valor, AMBIGUO, campo.alternativas)
    return campo


# ---------------------------------------------------------------------------
# Valor total
# ---------------------------------------------------------------------------
_VALOR = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+,\s?\d{2}|\d+,\s?\d{2}|\d+\.\d{2})(?![\d,]|\.\d|\s?%)"
)
# Linhas com valores que não são o total da nota.
_LINHA_NAO_TOTAL = re.compile(
    r"TROCO|SUB-?\s?TOTAL|DESCONTO|ACRESCIMO|TRIBUTO|IMPOSTO|LEI 12\.?741|ITENS|\bITEM\b"
    r"|DINHEIRO|RECEBIDO|TAXA|GORJETA|\bQTD|\bQTDE|UNIT"
)
_LINHA_A_PAGAR = re.compile(r"(?:VALOR|TOTAL)\s+A\s+PAGAR")
_LINHA_TOTAL = re.compile(r"\bTOTAL\b")


def _ler_dinheiro(texto: str) -> Decimal | None:
    bruto = texto.replace(" ", "")
    if "," in bruto:
        bruto = bruto.replace(".", "").replace(",", ".")
    try:
        valor = Decimal(bruto)
    except InvalidOperation:
        return None
    return valor if 0 < valor <= VALOR_MAXIMO else None


def _valores(linha: str) -> list[Decimal]:
    valores = (_ler_dinheiro(m) for m in _VALOR.findall(linha))
    return [v for v in valores if v is not None]


def _valor_total(linhas: list[str], avisos: list[str]) -> Campo:
    a_pagar: list[Decimal] = []
    totais: list[Decimal] = []
    todos: list[Decimal] = []
    for i, linha in enumerate(linhas):
        if _LINHA_NAO_TOTAL.search(linha):
            continue
        valores = _valores(linha)
        todos += valores
        if _LINHA_A_PAGAR.search(linha):
            destino = a_pagar
        elif _LINHA_TOTAL.search(linha):
            destino = totais
        else:
            continue
        if valores:
            destino.append(valores[-1])
        elif i + 1 < len(linhas) and not _LINHA_NAO_TOTAL.search(linhas[i + 1]):
            # O OCR às vezes separa o rótulo ("VALOR TOTAL R$") do número.
            destino.extend(_valores(linhas[i + 1])[:1])

    candidatos = a_pagar or totais
    if not candidatos:
        if not todos:
            return Campo()
        avisos.append("Não achamos o total na nota. Confira o valor.")
        return Campo(f"{max(todos):.2f}", AMBIGUO)
    # O maior primeiro: entre totais diferentes, o geral costuma ser o maior.
    ordenados = sorted(dict.fromkeys(candidatos), reverse=True)
    return _campo([f"{v:.2f}" for v in ordenados])


# ---------------------------------------------------------------------------
# Estabelecimento
# ---------------------------------------------------------------------------
_ROTULO_NOME = re.compile(r"RAZAO SOCIAL|NOME EMPRESARIAL|EMITENTE")
_NAO_E_NOME = re.compile(
    r"CNPJ|CPF|\bI\.?E\b|INSCRICAO|ENDERECO|\bRUA\b|\bR\.|\bAV\b|AVENIDA|RODOVIA|\bCEP\b"
    r"|\bTEL|FONE|DOCUMENTO|DANFE|NFC-?E|NF-?E|CUPOM|EXTRATO|\bSAT\b|NOTA FISCAL|CONSUMIDOR"
    r"|BAIRRO|EMISSAO|PROTOCOLO|CHAVE|HTTP|WWW|@"
)


def _limpar_nome(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip(" -:*.,|")[:MAX_NOME]


def _parece_nome(original: str, normalizada: str) -> bool:
    if _NAO_E_NOME.search(normalizada) or _DATA.search(normalizada):
        return False
    letras = sum(c.isalpha() for c in original)
    visiveis = sum(not c.isspace() for c in original)
    return letras >= 3 and letras >= visiveis / 2


def _estabelecimento(originais: list[str], linhas: list[str], linha_cnpj: int | None) -> Campo:
    # 1. Rótulo explícito ("Razão social: …"), na mesma linha ou na seguinte.
    for i, linha in enumerate(linhas):
        if not _ROTULO_NOME.search(linha) or _LINHA_CONSUMIDOR.search(linha):
            continue
        _, dois_pontos, resto = originais[i].partition(":")
        if dois_pontos and _parece_nome(resto, _normalizar(resto)):
            return Campo(_limpar_nome(resto), IDENTIFICADO)
        if i + 1 < len(linhas) and _parece_nome(originais[i + 1], linhas[i + 1]):
            return Campo(_limpar_nome(originais[i + 1]), IDENTIFICADO)

    # 2. Junto do CNPJ do emitente: na mesma linha, antes dele, ou logo acima.
    if linha_cnpj is not None:
        antes, *depois = re.split(r"(?i)cnpj", originais[linha_cnpj], maxsplit=1)
        if depois and _parece_nome(antes, _normalizar(antes)):
            return Campo(_limpar_nome(antes), IDENTIFICADO)
        for i in (linha_cnpj - 1, linha_cnpj - 2):
            if i >= 0 and _parece_nome(originais[i], linhas[i]):
                return Campo(_limpar_nome(originais[i]), IDENTIFICADO)

    # 3. Palpite: o nome costuma vir no topo da nota.
    for original, linha in list(zip(originais, linhas, strict=True))[:6]:
        if _parece_nome(original, linha):
            return Campo(_limpar_nome(original), AMBIGUO)
    return Campo()


# ---------------------------------------------------------------------------
# Número do documento
# ---------------------------------------------------------------------------
_NUMEROS = (
    re.compile(
        r"\b(?:NFC-?E|NFS-?E|NF-?E|NOTA FISCAL|CUPOM FISCAL|EXTRATO)\b\D{0,15}?"
        r"\bN(?:UMERO|RO|O|°)?\.?\s*:?\s*(\d{1,15})\b"
    ),
    re.compile(r"\bN(?:UMERO|RO\.?|O\.|O|°)\s*:?\s*(\d{1,15})\b"),
    re.compile(r"\bCOO\s*:?\s*(\d{1,15})\b"),
)
_LINHA_ENDERECO = re.compile(
    r"\bRUA\b|\bAV\b|AVENIDA|RODOVIA|ESTRADA|ALAMEDA|PRACA|TRAVESSA|BAIRRO|\bCEP\b|\bKM\b"
)


def _numero(linhas: list[str], chave: str | None) -> Campo:
    if chave:
        return Campo(str(int(chave[25:34])), IDENTIFICADO)
    numeros = []
    for linha in linhas:
        if _LINHA_ENDERECO.search(linha):
            continue
        for padrao in _NUMEROS:
            achado = padrao.search(linha)
            if achado and int(achado.group(1)) > 0:
                numeros.append(str(int(achado.group(1))))
                break
    return _campo(numeros)


# ---------------------------------------------------------------------------
# Categoria (só chaves de CATEGORIAS_VIAGEM; na dúvida, nenhuma)
# ---------------------------------------------------------------------------
_PALAVRAS_CATEGORIA: dict[str, tuple[str, ...]] = {
    "refeicao": (
        "RESTAURANTE",
        "LANCHONETE",
        "LANCHES?",
        "PADARIA",
        "PANIFICADORA",
        "CHURRASCARIA",
        "PIZZARIA",
        "CANTINA",
        "REFEIC(?:AO|OES)",
        "SELF[- ]?SERVICE",
        "MARMITEX?",
        "CAFETERIA",
        "BURGU?ER",
        "IFOOD",
        "UBER EATS",
    ),
    "hospedagem": ("HOTE(?:L|IS)", "POUSADA", "HOSPEDAGEM", "HOSTEL"),
    "combustivel": ("POSTO", "COMBUSTIVE(?:L|IS)", "GASOLINA", "ETANOL", "DIESEL", "GNV"),
    "estacionamento_pedagio": (
        "ESTACIONAMENTO",
        "PEDAGIO",
        "PARKING",
        "SEM PARAR",
        "CONECTCAR",
        "VELOE",
    ),
    "taxi_uber": ("UBER", "TAXI", "CABIFY", "99APP", "99POP", "99 TECNOLOGIA"),
    "passagem_aerea": (
        "PASSAGEM AEREA",
        "LINHAS AEREAS",
        "LATAM",
        "CARTAO DE EMBARQUE",
        "BILHETE AEREO",
    ),
    "translado_onibus": ("RODOVIARIA", "VIACAO", "BILHETE DE PASSAGEM", "BP-E", "ONIBUS"),
    "correios_cartorios": (
        "CORREIOS",
        "CARTORIO",
        "TABELIA(?:O|TO)",
        "TABELIONATO",
        "REGISTRO CIVIL",
        "OFICIAL DE REGISTRO",
    ),
    "lavanderia": ("LAVANDERIA",),
}
_PADROES_CATEGORIA = {
    categoria: [re.compile(rf"\b{p}\b") for p in palavras]
    for categoria, palavras in _PALAVRAS_CATEGORIA.items()
    if categoria in CATEGORIAS_VIAGEM
}


def _categoria(linhas: list[str]) -> Campo:
    texto = "\n".join(linhas)
    pontos = {
        categoria: sum(bool(p.search(texto)) for p in padroes)
        for categoria, padroes in _PADROES_CATEGORIA.items()
    }
    pontos = {c: n for c, n in pontos.items() if n}
    if not pontos:
        return Campo()
    maximo = max(pontos.values())
    empatadas = [c for c, n in pontos.items() if n == maximo]
    return _campo(empatadas)
