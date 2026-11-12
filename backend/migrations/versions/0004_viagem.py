"""viagem — campos do reembolso de viagem

Revision ID: 0004_viagem
Revises: 0003_gestores_grupo
Create Date: 2026-10-09

Reembolso de viagem usa a mesma tabela `solicitacoes` (tipo "viagem"), com
destino e período da viagem, e várias `despesas`, cada uma com descrição.
Todas as colunas novas aceitam nulo: as solicitações de alimentação não mudam.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_viagem"
down_revision: str | None = "0003_gestores_grupo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("solicitacoes", sa.Column("destino", sa.String(200), nullable=True))
    op.add_column("solicitacoes", sa.Column("viagem_inicio", sa.Date(), nullable=True))
    op.add_column("solicitacoes", sa.Column("viagem_fim", sa.Date(), nullable=True))
    op.add_column("despesas", sa.Column("descricao", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("despesas", "descricao")
    op.drop_column("solicitacoes", "viagem_fim")
    op.drop_column("solicitacoes", "viagem_inicio")
    op.drop_column("solicitacoes", "destino")
