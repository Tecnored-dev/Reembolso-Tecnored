"""Sessão de login persistida no banco.

O Hello-World guarda sessões num dict em memória ("em produção use Redis"):
reiniciar o container desloga todo mundo. Aqui ficam numa tabela. O cookie
leva o token; o banco guarda só o hash SHA-256 dele (vazou o banco, não vaza
sessão utilizável).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Sessao(Base):
    __tablename__ = "sessoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    # Object IDs dos grupos Azure, separados por vírgula (só para auditoria).
    grupos: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Papéis resolvidos no login: "gestor,financeiro" etc. (colaborador é implícito)
    papeis: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    via: Mapped[str] = mapped_column(String(20), nullable=False, default="microsoft")
    criado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expira_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("uq_sessoes_token_hash", "token_hash", unique=True),
        Index("ix_sessoes_expira_em", "expira_em"),
    )
