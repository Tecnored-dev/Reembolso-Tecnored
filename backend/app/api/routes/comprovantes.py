"""Leitura automática de comprovantes: foto ou PDF → sugestões para o formulário.

Só LÊ: não grava o arquivo, não cria solicitação e não guarda o resultado. O
colaborador confere e corrige os campos e envia o pedido pelas rotas de sempre.
Feito para servir também ao futuro app do celular (contrato no OpenAPI).
"""

from __future__ import annotations

import logging
import threading
import time
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth.deps import usuario_atual
from app.auth.sessoes import Usuario
from app.config import ARQUIVO_TAMANHO_MAX, OCR_ANALISES_SIMULTANEAS, OCR_ESPERA_VAGA_SEGUNDOS
from app.ocr.extracao import extrair_texto
from app.ocr.interpretacao import AMBIGUO, ILEGIVEL, Campo, interpretar
from app.ocr.motor import FalhaOcr, MotorOcr, MotorTesseract, TempoEsgotado
from app.services import arquivos as servico_arquivos
from app.services.arquivos import ArquivoValidado

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/comprovantes", tags=["comprovantes"])

# OCR é pesado em CPU: poucas leituras ao mesmo tempo, para não atrapalhar o resto
# da API nem os outros sistemas do servidor.
_VAGAS = threading.BoundedSemaphore(OCR_ANALISES_SIMULTANEAS)

MENSAGEM_INDISPONIVEL = "A leitura automática não está disponível agora. Preencha os dados à mão."
MENSAGEM_TEMPO = "A leitura demorou demais. Preencha os dados à mão."

Estado = Literal["identificado", "ambiguo", "nao_identificado"]


class CampoLido(BaseModel):
    valor: str | None
    estado: Estado
    alternativas: list[str]


class CamposLidos(BaseModel):
    data: CampoLido  # AAAA-MM-DD
    valor_total: CampoLido  # "48.90"
    estabelecimento: CampoLido
    cnpj: CampoLido  # 14 caracteres, sem pontuação
    numero_documento: CampoLido
    categoria_sugerida: CampoLido  # id de /api/cadastros → categorias_viagem


class Analise(BaseModel):
    """Sugestões para o formulário. Nenhum campo é garantido: o colaborador confere."""

    status: Literal["lido", "parcial", "ilegivel"]
    origem: Literal["texto_pdf", "ocr"] | None
    campos: CamposLidos
    avisos: list[str]


class Erro(BaseModel):
    detail: str


@lru_cache
def get_motor() -> MotorOcr:
    return MotorTesseract()


def _campo(campo: Campo) -> CampoLido:
    return CampoLido(valor=campo.valor, estado=campo.estado, alternativas=list(campo.alternativas))


def _ilegivel(origem: str | None, aviso: str) -> Analise:
    vazio = _campo(Campo())
    return Analise(
        status=ILEGIVEL,
        origem=origem,
        campos=CamposLidos(
            data=vazio,
            valor_total=vazio,
            estabelecimento=vazio,
            cnpj=vazio,
            numero_documento=vazio,
            categoria_sugerida=vazio,
        ),
        avisos=[aviso],
    )


def _analisar(arquivo: ArquivoValidado, motor: MotorOcr) -> Analise | None:
    """None = sem vaga agora (o OCR está ocupado com outras leituras)."""
    if not _VAGAS.acquire(timeout=OCR_ESPERA_VAGA_SEGUNDOS):
        return None
    try:
        extraido = extrair_texto(arquivo, motor)
    except TempoEsgotado:
        return _ilegivel("ocr", MENSAGEM_TEMPO)
    finally:
        _VAGAS.release()
    leitura = interpretar(extraido.texto)
    return Analise(
        status=leitura.status,
        origem=extraido.origem,
        campos=CamposLidos(
            data=_campo(leitura.data),
            valor_total=_campo(leitura.valor_total),
            estabelecimento=_campo(leitura.estabelecimento),
            cnpj=_campo(leitura.cnpj),
            numero_documento=_campo(leitura.numero_documento),
            categoria_sugerida=_campo(leitura.categoria_sugerida),
        ),
        avisos=[*extraido.avisos, *leitura.avisos],
    )


@router.post(
    "/analisar",
    response_model=Analise,
    responses={
        400: {"model": Erro, "description": "Arquivo inválido (formato, tamanho ou corrompido)."},
        401: {"model": Erro, "description": "Não autenticado."},
        503: {"model": Erro, "description": "Leitura ocupada ou indisponível: preencher à mão."},
    },
)
async def analisar(
    arquivo: UploadFile = File(..., description="Foto (JPG, PNG) ou PDF da nota, até 10 MB."),
    usuario: Usuario = Depends(usuario_atual),
    motor: MotorOcr = Depends(get_motor),
):
    """Lê o comprovante e sugere data, valor total, estabelecimento, CNPJ, número
    e categoria. Cada campo vem "identificado", "ambiguo" (com alternativas) ou
    "nao_identificado". Não grava nada."""
    conteudo = await arquivo.read(ARQUIVO_TAMANHO_MAX + 1)
    validado = servico_arquivos.validar(conteudo, arquivo.filename)

    inicio = time.monotonic()
    try:
        analise = await run_in_threadpool(_analisar, validado, motor)
    except FalhaOcr:
        log.warning("Leitura de comprovante: falha no motor de OCR.")
        return JSONResponse(status_code=503, content={"detail": MENSAGEM_INDISPONIVEL})
    if analise is None:
        log.warning(
            "Leitura de comprovante: sem vaga (%s leituras em andamento).",
            OCR_ANALISES_SIMULTANEAS,
        )
        return JSONResponse(status_code=503, content={"detail": MENSAGEM_INDISPONIVEL})

    # Só metadados: nada do conteúdo da nota vai para o log (LGPD).
    ambiguos = sum(
        getattr(analise.campos, nome).estado == AMBIGUO for nome in CamposLidos.model_fields
    )
    log.info(
        "Leitura de comprovante: %s, %s, %s, %.1fs, %s campo(s) ambíguo(s).",
        validado.tipo,
        analise.origem,
        analise.status,
        time.monotonic() - inicio,
        ambiguos,
    )
    return analise
