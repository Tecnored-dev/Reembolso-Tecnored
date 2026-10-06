"""Validação e gravação dos arquivos das notas (foto ou PDF)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.config import ARQUIVO_TAMANHO_MAX
from app.services.erros import RegraNegocio
from app.storage import Armazenamento

# Tipo é decidido pelos primeiros bytes do arquivo, não pela extensão nem pelo
# content-type que o navegador diz (os dois são fáceis de falsificar).
_ASSINATURAS: list[tuple[bytes, str, str]] = [
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"%PDF-", "application/pdf", ".pdf"),
]


@dataclass(frozen=True)
class ArquivoValidado:
    conteudo: bytes
    nome: str
    tipo: str
    extensao: str


def validar(conteudo: bytes, nome_original: str | None) -> ArquivoValidado:
    if not conteudo:
        raise RegraNegocio("Anexe a foto ou o PDF da nota.")
    if len(conteudo) > ARQUIVO_TAMANHO_MAX:
        limite_mb = ARQUIVO_TAMANHO_MAX // (1024 * 1024)
        raise RegraNegocio(f"Arquivo maior que {limite_mb} MB.")
    for assinatura, tipo, extensao in _ASSINATURAS:
        if conteudo.startswith(assinatura):
            nome = (nome_original or f"nota{extensao}").strip()[-255:] or f"nota{extensao}"
            return ArquivoValidado(conteudo, nome, tipo, extensao)
    raise RegraNegocio("Formato não aceito. Envie JPG, PNG ou PDF.")


def salvar(
    armazenamento: Armazenamento, arquivo: ArquivoValidado, codigo: str, agora: datetime
) -> str:
    """Grava e devolve a chave (ex.: 2026/10/REE-000012/3f2a....jpg)."""
    chave = f"{agora:%Y/%m}/{codigo}/{uuid.uuid4().hex}{arquivo.extensao}"
    armazenamento.salvar(chave, arquivo.conteudo, arquivo.tipo)
    return chave
