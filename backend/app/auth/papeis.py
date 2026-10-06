"""Papéis a partir dos grupos do Azure AD.

Diferente do Hello-World (sem grupo = sem acesso): aqui todo usuário do
domínio é colaborador e pode pedir reembolso (ok da TI em 29/09/2026). Os
grupos de segurança só acrescentam papéis especiais.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.config import Settings

COLABORADOR = "colaborador"
GESTOR = "gestor"
FINANCEIRO = "financeiro"
ADMIN = "admin"
PAPEIS_ESPECIAIS = (GESTOR, FINANCEIRO, ADMIN)


def resolver_papeis(grupos: Iterable[str], settings: Settings) -> list[str]:
    ids = set(grupos)
    mapa = {
        GESTOR: settings.grupo_gestor,
        FINANCEIRO: settings.grupo_financeiro,
        ADMIN: settings.grupo_admin,
    }
    return [papel for papel, grupo in mapa.items() if grupo and grupo in ids]


def papeis_publicos(papeis_especiais: Iterable[str]) -> list[str]:
    """Lista para o frontend: colaborador sempre, mais os especiais."""
    return [COLABORADOR, *[p for p in PAPEIS_ESPECIAIS if p in set(papeis_especiais)]]
