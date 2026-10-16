"""Separação entre usuários de teste (painel "Ver como") e usuários reais.

Os de teste usam um domínio que não existe (`.invalid`): nenhum aviso chega a
ninguém de verdade, e pedidos de teste e reais nunca se misturam (listas,
gestores e notificações).
"""

from __future__ import annotations

DOMINIO_TESTE = "@painel-teste.tecnored.invalid"


def eh_teste(email: str | None) -> bool:
    return bool(email) and email.strip().lower().endswith(DOMINIO_TESTE)
