"""sessoes — sessão de login persistida

Revision ID: 0001_sessoes
Revises:
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_sessoes"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sessoes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("grupos", sa.Text(), nullable=True),
        sa.Column("papeis", sa.String(100), nullable=False, server_default=""),
        sa.Column("via", sa.String(20), nullable=False, server_default="microsoft"),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("expira_em", sa.DateTime(), nullable=False),
    )
    op.create_index("uq_sessoes_token_hash", "sessoes", ["token_hash"], unique=True)
    op.create_index("ix_sessoes_expira_em", "sessoes", ["expira_em"])


def downgrade() -> None:
    op.drop_table("sessoes")
