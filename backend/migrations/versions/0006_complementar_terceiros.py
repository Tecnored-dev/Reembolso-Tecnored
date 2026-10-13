"""complementar e terceiros — diária complementar somada e pedido em nome de outra pessoa

Revision ID: 0006_complementar_terceiros
Revises: 0005_adiantamento
Create Date: 2026-10-13

- Diária complementar: passa a SOMAR às diárias normais (Thais, 13/10). O valor
  informado vai para `valor_complementar`; o booleano `diaria_complementar` sai.
  Pedidos antigos com complementar (só em bancos de teste) guardam o valor total
  como complementar.
- Pedido em nome de outra pessoa: `criado_por_email`/`criado_por_nome` guardam
  quem preencheu; o solicitante passa a ser quem recebe.
- Empresa de débito: "inicialmente só Tecnored" no sistema inteiro (Nirlene,
  13/10). A TECNORED MARABA fica INATIVA (some da lista); pedidos antigos não
  mudam, porque guardam o nome da empresa. Para voltar, basta reativar.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_complementar_terceiros"
down_revision: str | None = "0005_adiantamento"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("solicitacoes", sa.Column("valor_complementar", sa.Numeric(12, 2), nullable=True))
    op.execute("UPDATE solicitacoes SET valor_complementar = valor_total WHERE diaria_complementar")
    with op.batch_alter_table("solicitacoes") as tabela:
        tabela.drop_column("diaria_complementar")
    op.add_column("solicitacoes", sa.Column("criado_por_email", sa.String(254), nullable=True))
    op.add_column("solicitacoes", sa.Column("criado_por_nome", sa.String(200), nullable=True))
    op.create_index("ix_solicitacoes_criado_por", "solicitacoes", ["criado_por_email"])
    op.execute("UPDATE empresas SET ativo = false WHERE nome = 'TECNORED MARABA'")


def downgrade() -> None:
    op.execute("UPDATE empresas SET ativo = true WHERE nome = 'TECNORED MARABA'")
    op.drop_index("ix_solicitacoes_criado_por", table_name="solicitacoes")
    op.drop_column("solicitacoes", "criado_por_nome")
    op.drop_column("solicitacoes", "criado_por_email")
    op.add_column("solicitacoes", sa.Column("diaria_complementar", sa.Boolean(), nullable=True))
    op.execute("UPDATE solicitacoes SET diaria_complementar = (valor_complementar IS NOT NULL)")
    op.drop_column("solicitacoes", "valor_complementar")
