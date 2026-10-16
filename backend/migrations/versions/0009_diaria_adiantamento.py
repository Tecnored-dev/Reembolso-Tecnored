"""diaria e adiantamento — linhas de diária e viagem internacional

Revision ID: 0009_diaria_adiantamento
Revises: 0008_recusa_centro_custo
Create Date: 2026-10-15

Regras da Thais (15/10/2026):
- Diária de Viagem: o pedido tem linhas "Valor Integral" (valor fixo) ou
  "Valor Parcial" (valor informado), com quantidade de diárias, e o campo
  "Viagem internacional?" (internacional não tem diária).
- Adiantamento: o colaborador informa o valor (vai em `valor_total`); as
  colunas `diarias` e `valor_complementar` ficam só para os pedidos antigos.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_diaria_adiantamento"
down_revision: str | None = "0008_recusa_centro_custo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("solicitacoes", sa.Column("viagem_internacional", sa.Boolean(), nullable=True))
    op.create_table(
        "linhas_diaria",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "solicitacao_id",
            sa.Integer(),
            sa.ForeignKey("solicitacoes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("quantidade", sa.Integer(), nullable=False),
        sa.Column("valor_unitario", sa.Numeric(12, 2), nullable=False),
    )
    op.create_index("ix_linhas_diaria_solicitacao", "linhas_diaria", ["solicitacao_id"])


def downgrade() -> None:
    op.drop_index("ix_linhas_diaria_solicitacao", table_name="linhas_diaria")
    op.drop_table("linhas_diaria")
    op.drop_column("solicitacoes", "viagem_internacional")
