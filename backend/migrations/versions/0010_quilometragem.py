"""quilometragem — km e percurso na nota, arquivo opcional

Revision ID: 0010_quilometragem
Revises: 0009_diaria_adiantamento
Create Date: 2026-10-22

Regras da Thais (22/10/2026): quilometragem com veículo próprio vale R$ 1,00
por km, não tem comprovante e só existe no reembolso. A nota guarda os km e o
percurso (origem, paradas e destino, em JSON). Como não há comprovante, as
colunas do arquivo passam a aceitar vazio.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_quilometragem"
down_revision: str | None = "0009_diaria_adiantamento"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("despesas") as lote:
        lote.add_column(sa.Column("km", sa.Numeric(8, 1), nullable=True))
        lote.add_column(sa.Column("percurso", sa.Text(), nullable=True))
        lote.alter_column("arquivo_chave", existing_type=sa.String(300), nullable=True)
        lote.alter_column("arquivo_nome", existing_type=sa.String(255), nullable=True)
        lote.alter_column("arquivo_tipo", existing_type=sa.String(60), nullable=True)
        lote.alter_column("arquivo_tamanho", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    # Só desfaz se não existir nota sem arquivo (as de quilometragem).
    op.execute("DELETE FROM despesas WHERE arquivo_chave IS NULL")
    with op.batch_alter_table("despesas") as lote:
        lote.alter_column("arquivo_tamanho", existing_type=sa.Integer(), nullable=False)
        lote.alter_column("arquivo_tipo", existing_type=sa.String(60), nullable=False)
        lote.alter_column("arquivo_nome", existing_type=sa.String(255), nullable=False)
        lote.alter_column("arquivo_chave", existing_type=sa.String(300), nullable=False)
        lote.drop_column("percurso")
        lote.drop_column("km")
