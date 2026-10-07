"""Ajustes de log.

O log de acesso do Uvicorn grava a URL completa de cada requisição. No
`/auth/callback` ela traz o código de autorização da Microsoft (uso único,
vale poucos minutos), e não há motivo para guardar isso em log. Este filtro
troca a query string dessas rotas por "?…".
"""

from __future__ import annotations

import logging

ROTAS_SENSIVEIS = ("/auth/callback",)


class OcultarQuerySensivel(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Formato do uvicorn.access: (cliente, método, caminho, versão, status)
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            caminho = args[2]
            base, _, query = caminho.partition("?")
            if query and base in ROTAS_SENSIVEIS:
                record.args = (*args[:2], f"{base}?…", *args[3:])
        return True


def instalar() -> None:
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, OcultarQuerySensivel) for f in logger.filters):
        logger.addFilter(OcultarQuerySensivel())
