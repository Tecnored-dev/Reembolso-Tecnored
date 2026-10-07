"""gestores_grupo — cópia do grupo de gestores do Azure, atualizada no login

Revision ID: 0003_gestores_grupo
Revises: 0002_alimentacao
Create Date: 2026-10-07

A TI liberou GroupMember.Read.All DELEGADA: o grupo só pode ser lido em nome de
quem está logando, então a lista é guardada aqui a cada login.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_gestores_grupo"
down_revision: str | None = "0002_alimentacao"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gestores_grupo",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("gestores_grupo")
