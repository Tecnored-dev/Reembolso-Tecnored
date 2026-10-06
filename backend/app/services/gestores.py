"""Lista de gestores para o colaborador escolher.

Orientação do Marcos (TI): listar do grupo de gestores do Azure, em vez de
manter tabela própria. Isso usa o Microsoft Graph com token de APLICAÇÃO
(permissão GroupMember.Read.All de aplicativo — em validação pela TI).

Enquanto o Graph não responder (local, permissão pendente, fora do ar), cai
para quem já entrou no sistema com o papel de gestor. A queda é registrada
em log; a lista nunca fica vazia por erro de rede se houver gestor conhecido.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx
from msal import ConfidentialClientApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.papeis import GESTOR
from app.config import Settings
from app.models.cadastros import Usuario

log = logging.getLogger(__name__)

CACHE_SEGUNDOS = 600
_cache: dict[str, tuple[float, list[Gestor]]] = {}


@dataclass(frozen=True)
class Gestor:
    email: str
    nome: str


def _do_graph(settings: Settings) -> list[Gestor]:
    app = ConfidentialClientApplication(
        settings.azure_client_id,
        authority=f"https://login.microsoftonline.com/{settings.azure_tenant_id}",
        client_credential=settings.azure_client_secret,
    )
    token = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in token:
        raise RuntimeError(token.get("error_description") or token.get("error") or "sem token")

    url: str | None = (
        f"https://graph.microsoft.com/v1.0/groups/{settings.grupo_gestor}"
        "/transitiveMembers/microsoft.graph.user?$select=displayName,mail,userPrincipalName"
        "&$top=999"
    )
    gestores: list[Gestor] = []
    with httpx.Client(timeout=10.0) as client:
        while url:
            resp = client.get(url, headers={"Authorization": f"Bearer {token['access_token']}"})
            resp.raise_for_status()
            dados = resp.json()
            for membro in dados.get("value", []):
                email = (membro.get("mail") or membro.get("userPrincipalName") or "").lower()
                if email:
                    gestores.append(Gestor(email, membro.get("displayName") or email))
            url = dados.get("@odata.nextLink")
    return gestores


def _do_banco(db: Session) -> list[Gestor]:
    usuarios = db.scalars(select(Usuario).where(Usuario.papeis.contains(GESTOR))).all()
    return [Gestor(u.email, u.nome) for u in usuarios if GESTOR in u.lista_papeis]


def listar(db: Session, settings: Settings) -> list[Gestor]:
    if settings.azure_configurado and settings.grupo_gestor:
        guardado = _cache.get(settings.grupo_gestor)
        if guardado and time.monotonic() - guardado[0] < CACHE_SEGUNDOS:
            gestores = guardado[1]
        else:
            try:
                gestores = _do_graph(settings)
                _cache[settings.grupo_gestor] = (time.monotonic(), gestores)
            except Exception as exc:  # rede, permissão, grupo errado...
                log.warning("Graph indisponível para listar gestores (%s); usando o banco.", exc)
                gestores = _do_banco(db)
    else:
        gestores = _do_banco(db)
    unicos = {g.email: g for g in gestores}
    return sorted(unicos.values(), key=lambda g: g.nome.lower())


def buscar(db: Session, settings: Settings, email: str) -> Gestor | None:
    email = email.strip().lower()
    return next((g for g in listar(db, settings) if g.email == email), None)
