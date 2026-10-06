"""Backend "local": arquivos numa pasta (volume /data em Docker).

Bom para desenvolver e para começar; em hml/main só serve se o volume tiver
backup. Chaves são caminhos relativos ("2026/10/REE-00012/abc.jpg") — nunca
aceitamos ".." nem caminho absoluto.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.storage.base import ArquivoNaoEncontrado


class ArmazenamentoLocal:
    def __init__(self, raiz: str) -> None:
        self.raiz = Path(raiz)

    def _caminho(self, chave: str) -> Path:
        destino = (self.raiz / chave).resolve()
        if self.raiz.resolve() not in destino.parents:
            raise ValueError(f"Chave inválida: {chave!r}")
        return destino

    def salvar(self, chave: str, conteudo: bytes, content_type: str) -> None:
        destino = self._caminho(chave)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)

    def abrir(self, chave: str) -> bytes:
        caminho = self._caminho(chave)
        if not caminho.is_file():
            raise ArquivoNaoEncontrado(chave)
        return caminho.read_bytes()

    def remover(self, chave: str) -> None:
        self._caminho(chave).unlink(missing_ok=True)

    def saudavel(self) -> bool:
        try:
            self.raiz.mkdir(parents=True, exist_ok=True)
            return os.access(self.raiz, os.W_OK)
        except OSError:
            return False
