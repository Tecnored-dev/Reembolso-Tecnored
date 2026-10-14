"""motivo e local — motivo da despesa e local da refeição

Revision ID: 0007_motivo_local
Revises: 0006_complementar_terceiros
Create Date: 2026-10-13

Alimentação e despesas diversas ganham o MOTIVO (lista do ARGO, obrigatório
nos pedidos novos) e a alimentação ganha o LOCAL da refeição (Pindamonhangaba,
Marabá ou outro), que define o limite do alerta (R$ 40, R$ 45 ou R$ 135).
Aceitam nulo: pedidos antigos ficam sem motivo e sem local.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_motivo_local"
down_revision: str | None = "0006_complementar_terceiros"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("solicitacoes", sa.Column("motivo", sa.String(60), nullable=True))
    op.add_column("solicitacoes", sa.Column("local_refeicao", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("solicitacoes", "local_refeicao")
    op.drop_column("solicitacoes", "motivo")
