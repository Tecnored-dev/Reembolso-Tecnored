"""recusa e centro de custo — recusa do gestor e centro de custo por pedido

Revision ID: 0008_recusa_centro_custo
Revises: 0007_motivo_local
Create Date: 2026-10-15

Regras da Thais (15/10/2026):
- O gestor não devolve mais: aprova ou RECUSA, e a recusa finaliza o pedido.
  Guardamos quem recusou, quando e o motivo.
- O centro de custo deixa de ser do perfil e passa a ser escolhido em cada
  pedido. O adiantamento não tem centro de custo, então a coluna aceita nulo.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_recusa_centro_custo"
down_revision: str | None = "0007_motivo_local"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("solicitacoes", sa.Column("recusado_por", sa.String(200), nullable=True))
    op.add_column("solicitacoes", sa.Column("recusado_em", sa.DateTime(), nullable=True))
    op.add_column("solicitacoes", sa.Column("motivo_recusa", sa.Text(), nullable=True))
    with op.batch_alter_table("solicitacoes") as batch:
        batch.alter_column("centro_custo", existing_type=sa.String(140), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE solicitacoes SET centro_custo = '' WHERE centro_custo IS NULL")
    with op.batch_alter_table("solicitacoes") as batch:
        batch.alter_column("centro_custo", existing_type=sa.String(140), nullable=False)
    op.drop_column("solicitacoes", "motivo_recusa")
    op.drop_column("solicitacoes", "recusado_em")
    op.drop_column("solicitacoes", "recusado_por")
