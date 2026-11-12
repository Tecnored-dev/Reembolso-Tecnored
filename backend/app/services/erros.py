"""Erros de regra de negócio — viram respostas HTTP nas rotas."""

from __future__ import annotations


class RegraNegocio(Exception):
    """Pedido inválido pela regra (400). A mensagem vai para o usuário."""


class SemPermissao(Exception):
    """Usuário não pode fazer isso nesta solicitação (403)."""


class NaoEncontrado(Exception):
    """Solicitação inexistente ou invisível para o usuário (404)."""
