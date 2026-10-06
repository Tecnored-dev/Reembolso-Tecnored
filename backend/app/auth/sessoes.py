"""Criação, leitura e encerramento de sessões persistidas."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import SESSION_DURATION_HOURS
from app.models.sessao import Sessao

COOKIE = "session_token"
DURACAO = timedelta(hours=SESSION_DURATION_HOURS)


def agora_utc() -> datetime:
    """Datetime naive em UTC (o banco guarda sem fuso)."""
    return datetime.now(UTC).replace(tzinfo=None)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class Usuario:
    email: str
    nome: str
    papeis: tuple[str, ...]  # só os especiais; colaborador é implícito
    via: str

    def tem(self, papel: str) -> bool:
        return papel in self.papeis


def criar_sessao(
    db: Session,
    *,
    email: str,
    nome: str,
    grupos: list[str],
    papeis: list[str],
    via: str,
) -> str:
    """Grava a sessão e devolve o token (vai só no cookie, nunca no banco)."""
    token = secrets.token_urlsafe(32)
    agora = agora_utc()
    db.add(
        Sessao(
            token_hash=_hash(token),
            email=email.strip().lower(),
            nome=nome,
            grupos=",".join(grupos) or None,
            papeis=",".join(papeis),
            via=via,
            criado_em=agora,
            expira_em=agora + DURACAO,
        )
    )
    # Aproveita para limpar sessões vencidas (barato, índice em expira_em).
    db.execute(delete(Sessao).where(Sessao.expira_em < agora))
    db.commit()
    return token


def obter_usuario(db: Session, token: str | None) -> Usuario | None:
    if not token:
        return None
    sessao = db.scalar(select(Sessao).where(Sessao.token_hash == _hash(token)))
    if sessao is None or sessao.expira_em < agora_utc():
        return None
    papeis = tuple(p for p in sessao.papeis.split(",") if p)
    return Usuario(email=sessao.email, nome=sessao.nome, papeis=papeis, via=sessao.via)


def encerrar_sessao(db: Session, token: str | None) -> str | None:
    """Apaga a sessão; devolve o `via` dela (para o logout do Cloudflare)."""
    if not token:
        return None
    sessao = db.scalar(select(Sessao).where(Sessao.token_hash == _hash(token)))
    if sessao is None:
        return None
    via = sessao.via
    db.delete(sessao)
    db.commit()
    return via
