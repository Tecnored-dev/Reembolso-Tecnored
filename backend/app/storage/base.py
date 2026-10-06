"""Contrato do armazenamento de arquivos (qualquer backend implementa isto)."""

from __future__ import annotations

from typing import Protocol


class ArquivoNaoEncontrado(Exception):
    pass


class Armazenamento(Protocol):
    def salvar(self, chave: str, conteudo: bytes, content_type: str) -> None: ...

    def abrir(self, chave: str) -> bytes: ...

    def remover(self, chave: str) -> None: ...

    def saudavel(self) -> bool:
        """Usado pelo /health: o backend consegue gravar/ler agora?"""
        ...
