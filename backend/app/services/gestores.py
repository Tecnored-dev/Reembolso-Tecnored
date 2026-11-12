"""Lista de gestores para o colaborador escolher.

Orientação do Marcos (TI): listar do grupo de gestores do Azure
(`AZURE_GROUP_GESTOR`), em vez de manter cadastro próprio.

A TI liberou a permissão `GroupMember.Read.All` do tipo DELEGADA (06/10/2026):
ela só vale em nome de alguém logado. Por isso a lista é lida durante o LOGIN
de qualquer pessoa (com o token dela) e guardada na tabela `gestores_grupo`.
Quem entra ou sai do grupo aparece/some no próximo login de qualquer usuário.
Nenhum token é guardado.

Ordem de consulta em `listar`:
1. a cópia do grupo salva no último login (`gestores_grupo`);
2. se ainda não houver cópia: Graph com token de APLICATIVO (só funciona se a
   TI um dia liberar a permissão do tipo Aplicativo);
3. por último: quem já entrou no sistema com o papel de gestor.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx
from msal import ConfidentialClientApplication
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.papeis import GESTOR
from app.config import Settings
from app.models.cadastros import GestorGrupo, Usuario
from app.services.isolamento import eh_teste

log = logging.getLogger(__name__)

CACHE_SEGUNDOS = 600
_cache: dict[str, tuple[float, list[Gestor]]] = {}


@dataclass(frozen=True)
class Gestor:
    email: str
    nome: str


def buscar_membros(token: str, grupo_id: str) -> list[Gestor]:
    """Membros (usuários, inclusive de subgrupos) de um grupo no Graph."""
    url: str | None = (
        f"https://graph.microsoft.com/v1.0/groups/{grupo_id}"
        "/transitiveMembers/microsoft.graph.user?$select=displayName,mail,userPrincipalName"
        "&$top=999"
    )
    gestores: list[Gestor] = []
    sem_email = 0
    with httpx.Client(timeout=10.0) as client:
        while url:
            resp = client.get(url, headers={"Authorization": f"Bearer {token}"})
            resp.raise_for_status()
            dados = resp.json()
            for membro in dados.get("value", []):
                email = (membro.get("mail") or membro.get("userPrincipalName") or "").lower()
                if email:
                    gestores.append(Gestor(email, membro.get("displayName") or email))
                else:
                    sem_email += 1
            url = dados.get("@odata.nextLink")
    if sem_email and not gestores:
        # O Graph devolve só o id quando falta permissão para ler o perfil dos
        # usuários (User.ReadBasic.All). Não dá para usar: melhor falhar alto.
        raise RuntimeError(
            f"o grupo tem {sem_email} membro(s), mas o Graph não devolveu nome nem e-mail "
            "(provável falta da permissão User.ReadBasic.All)"
        )
    if sem_email:
        log.warning("Grupo de gestores: %s membro(s) sem e-mail foram ignorados.", sem_email)
    return gestores


def sincronizar_no_login(db: Session, settings: Settings, token_usuario: str, agora) -> bool:
    """Atualiza a cópia do grupo de gestores usando o token de quem acabou de logar.

    Nunca derruba o login: em erro, registra em log e mantém a cópia anterior.
    Devolve True se atualizou.
    """
    if not settings.grupo_gestor:
        return False
    try:
        membros = buscar_membros(token_usuario, settings.grupo_gestor)
    except Exception as exc:  # permissão, rede, grupo errado...
        log.warning("Não foi possível ler o grupo de gestores no login (%s).", exc)
        return False
    unicos = {g.email: g for g in membros}
    log.warning("Grupo de gestores lido no login: %s membro(s).", len(unicos))
    # Atualiza só a diferença (em vez de apagar e regravar tudo a cada login) e num
    # savepoint: dois logins ao mesmo tempo inserindo o mesmo gestor novo não podem
    # derrubar o login de ninguém; quem perde a corrida só deixa para o outro.
    try:
        with db.begin_nested():
            atuais = {g.email: g for g in db.scalars(select(GestorGrupo)).all()}
            for email, antigo in atuais.items():
                if email not in unicos:
                    db.delete(antigo)
            for email, g in unicos.items():
                if email in atuais:
                    atuais[email].nome, atuais[email].atualizado_em = g.nome, agora
                else:
                    db.add(GestorGrupo(email=email, nome=g.nome, atualizado_em=agora))
            db.flush()
    except IntegrityError:
        log.info("Lista de gestores atualizada por outro login ao mesmo tempo; mantida.")
        return False
    _cache.clear()
    return True


def _do_graph_aplicativo(settings: Settings) -> list[Gestor]:
    app = ConfidentialClientApplication(
        settings.azure_client_id,
        authority=f"https://login.microsoftonline.com/{settings.azure_tenant_id}",
        client_credential=settings.azure_client_secret,
    )
    token = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in token:
        raise RuntimeError(token.get("error_description") or token.get("error") or "sem token")
    return buscar_membros(token["access_token"], settings.grupo_gestor)


def _da_copia(db: Session) -> list[Gestor]:
    return [Gestor(g.email, g.nome) for g in db.scalars(select(GestorGrupo)).all()]


def _de_quem_ja_entrou(db: Session) -> list[Gestor]:
    usuarios = db.scalars(select(Usuario).where(Usuario.papeis.contains(GESTOR))).all()
    return [Gestor(u.email, u.nome) for u in usuarios if GESTOR in u.lista_papeis]


def listar(db: Session, settings: Settings) -> list[Gestor]:
    gestores = _da_copia(db)
    if not gestores and settings.azure_configurado and settings.grupo_gestor:
        guardado = _cache.get(settings.grupo_gestor)
        if guardado and time.monotonic() - guardado[0] < CACHE_SEGUNDOS:
            gestores = guardado[1]
        else:
            try:
                gestores = _do_graph_aplicativo(settings)
                _cache[settings.grupo_gestor] = (time.monotonic(), gestores)
            except Exception as exc:
                log.info("Graph (aplicativo) indisponível para gestores (%s); usando o banco.", exc)
                _cache[settings.grupo_gestor] = (time.monotonic(), [])
    if not gestores:
        gestores = _de_quem_ja_entrou(db)
    unicos = {g.email: g for g in gestores}
    return sorted(unicos.values(), key=lambda g: g.nome.lower())


def _de_teste(settings: Settings) -> list[Gestor]:
    """Gestores do painel de teste (só quando ele está ligado)."""
    if not settings.painel_teste_enabled:
        return []
    from app.services.painel_teste import USUARIOS_TESTE

    return [Gestor(u.email, u.nome) for u in USUARIOS_TESTE if GESTOR in u.papeis]


def listar_para(db: Session, settings: Settings, email_usuario: str) -> list[Gestor]:
    """Quem pode ser escolhido por esse usuário: de teste só vê gestores de teste,
    e o usuário real nunca vê gestor de teste (pedidos de teste e reais não se misturam)."""
    if eh_teste(email_usuario):
        return sorted(_de_teste(settings), key=lambda g: g.nome.lower())
    return [g for g in listar(db, settings) if not eh_teste(g.email)]


def buscar(db: Session, settings: Settings, email: str) -> Gestor | None:
    email = email.strip().lower()
    return next(
        (g for g in [*listar(db, settings), *_de_teste(settings)] if g.email == email), None
    )
