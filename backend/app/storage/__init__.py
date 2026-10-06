"""Armazenamento dos arquivos das notas fiscais.

O banco guarda os dados da nota e a CHAVE do arquivo; o arquivo em si fica
num repositório de arquivos (orientação do Marcos, 30/09/2026). A TI ainda
decide entre S3 e SharePoint — por isso o resto do código só fala com a
interface `Armazenamento`, e trocar de backend é trocar `STORAGE_BACKEND`.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.storage.base import Armazenamento, ArquivoNaoEncontrado
from app.storage.local import ArmazenamentoLocal

__all__ = ["Armazenamento", "ArquivoNaoEncontrado", "get_armazenamento"]


@lru_cache
def get_armazenamento() -> Armazenamento:
    settings = get_settings()
    if settings.storage_backend == "local":
        return ArmazenamentoLocal(settings.storage_local_dir)
    # "s3" e "sharepoint" entram aqui quando a TI decidir.
    raise RuntimeError(f"STORAGE_BACKEND não suportado ainda: {settings.storage_backend!r}")
