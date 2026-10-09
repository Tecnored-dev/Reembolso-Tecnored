"""adiantamento — diárias, prestação de contas, devolução e diferença

Revision ID: 0005_adiantamento
Revises: 0004_viagem
Create Date: 2026-10-09

O adiantamento usa a mesma tabela `solicitacoes` (tipo "adiantamento"). O valor
adiantado fica em `valor_total`; as colunas novas guardam as diárias, o gasto
comprovado e quem fez cada etapa depois do pagamento. Todas aceitam nulo: as
solicitações de alimentação e de viagem não mudam.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_adiantamento"
down_revision: str | None = "0004_viagem"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUNAS = [
    ("diarias", sa.Integer()),
    ("diaria_complementar", sa.Boolean()),
    ("valor_gasto", sa.Numeric(12, 2)),
    ("prestacao_enviada_em", sa.DateTime()),
    ("prestacao_conferida_por", sa.String(200)),
    ("prestacao_conferida_em", sa.DateTime()),
    ("devolucao_confirmada_por", sa.String(200)),
    ("devolucao_confirmada_em", sa.DateTime()),
    ("diferenca_aprovada_por", sa.String(200)),
    ("diferenca_aprovada_em", sa.DateTime()),
    ("data_pagamento_diferenca", sa.Date()),
    ("encerrado_em", sa.DateTime()),
    ("lembrete_prestacao_em", sa.DateTime()),
    ("aviso_prestacao_vencida_em", sa.DateTime()),
]


def upgrade() -> None:
    for nome, tipo in _COLUNAS:
        op.add_column("solicitacoes", sa.Column(nome, tipo, nullable=True))


def downgrade() -> None:
    for nome, _tipo in reversed(_COLUNAS):
        op.drop_column("solicitacoes", nome)
