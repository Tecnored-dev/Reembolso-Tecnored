"""Cadastros de apoio: usuários (perfil), centros de custo e empresas de débito.

- Centro de custo: a lista oficial é a do formulário do Power Automate (Thais,
  06/10/2026). É sempre o do PRÓPRIO colaborador, então fica no perfil dele.
- Empresa de débito: o colaborador escolhe a cada solicitação.
- Usuário: criado/atualizado a cada login. Guarda o perfil (matrícula e centro
  de custo, informados no 1º acesso) e os papéis vistos no último login.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class CentroCusto(Base):
    __tablename__ = "centros_custo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    @property
    def rotulo(self) -> str:
        return f"{self.codigo} - {self.nome}"


class Empresa(Base):
    __tablename__ = "empresas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    matricula: Mapped[str | None] = mapped_column(String(30), nullable=True)
    centro_custo_id: Mapped[int | None] = mapped_column(
        ForeignKey("centros_custo.id"), nullable=True
    )
    # Papéis especiais do último login ("gestor,financeiro"); colaborador é implícito.
    papeis: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    ultimo_login_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    centro_custo: Mapped[CentroCusto | None] = relationship(lazy="joined")

    @property
    def lista_papeis(self) -> list[str]:
        return [p for p in self.papeis.split(",") if p]

    @property
    def perfil_completo(self) -> bool:
        # Só a matrícula (Thais, 15/10). O centro de custo agora é escolhido em
        # cada pedido; `centro_custo_id` guarda o último usado, para sugerir.
        return bool(self.matricula)


class GestorGrupo(Base):
    """Cópia dos membros do grupo de gestores do Azure, atualizada a cada login.

    Ver app/services/gestores.py: a permissão liberada pela TI é delegada, então
    o grupo só pode ser lido em nome de quem está logando.
    """

    __tablename__ = "gestores_grupo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
