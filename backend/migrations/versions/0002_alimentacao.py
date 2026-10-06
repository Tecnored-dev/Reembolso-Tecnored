"""alimentacao — cadastros, solicitações, despesas, histórico e notificações

Revision ID: 0002_alimentacao
Revises: 0001_sessoes
Create Date: 2026-10-06

Carga inicial:
- Centros de custo: lista do formulário do Power Automate (oficial, Thais 06/10/2026).
- Empresas de débito: as duas do ARGO.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_alimentacao"
down_revision: str | None = "0001_sessoes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DINHEIRO = sa.Numeric(12, 2)

CENTROS_CUSTO = [
    ("3110", "P&D - PROCESSOS"),
    ("3210", "P&D - DESENVOLVIMENTO"),
    ("3320", "LOGISTICA"),
    ("3330", "ALMOXARIFADO"),
    ("3350", "T.I / T.A"),
    ("3510", "MANUT ELETRICA / MECANICA"),
    ("3610", "P&D - Engenharia"),
    ("3710", "OPERACAO - STAFF"),
    ("3810", "BUSINESS DEVELOPEMENT"),
    ("4110", "CONTROLADORIA"),
    ("4120", "PESSOAS & CULTURA"),
    ("4140", "FACILITIES"),
    ("4150", "JURÍDICO / CONTRATOS"),
    ("4230", "SSMA"),
    ("4310", "SUPRIMENTOS"),
    ("4680", "GESTÃO EXECUTIVA PINDA"),
]
EMPRESAS = ["TECNORED", "TECNORED MARABA"]


def upgrade() -> None:
    centros = op.create_table(
        "centros_custo",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("codigo", sa.String(10), nullable=False, unique=True),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    empresas = op.create_table(
        "empresas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nome", sa.String(120), nullable=False, unique=True),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("matricula", sa.String(30), nullable=True),
        sa.Column("centro_custo_id", sa.Integer(), sa.ForeignKey("centros_custo.id")),
        sa.Column("papeis", sa.String(100), nullable=False, server_default=""),
        sa.Column("ultimo_login_em", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "solicitacoes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("codigo", sa.String(20), nullable=True, unique=True),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("solicitante_email", sa.String(254), nullable=False),
        sa.Column("solicitante_nome", sa.String(200), nullable=False),
        sa.Column("matricula", sa.String(30), nullable=False),
        sa.Column("centro_custo", sa.String(140), nullable=False),
        sa.Column("empresa", sa.String(120), nullable=False),
        sa.Column("gestor_email", sa.String(254), nullable=True),
        sa.Column("gestor_nome", sa.String(200), nullable=True),
        sa.Column("pula_gestor", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("moeda", sa.String(3), nullable=False, server_default="BRL"),
        sa.Column("valor_total", DINHEIRO, nullable=False),
        sa.Column("alerta_limite", sa.Text(), nullable=True),
        sa.Column("enviado_em", sa.DateTime(), nullable=False),
        sa.Column("conferido_por", sa.String(200), nullable=True),
        sa.Column("conferido_em", sa.DateTime(), nullable=True),
        sa.Column("aprovado_por", sa.String(200), nullable=True),
        sa.Column("aprovado_em", sa.DateTime(), nullable=True),
        sa.Column("pago_por", sa.String(200), nullable=True),
        sa.Column("pago_em", sa.DateTime(), nullable=True),
        sa.Column("data_pagamento", sa.Date(), nullable=True),
        sa.Column("devolvido_por", sa.String(200), nullable=True),
        sa.Column("devolvido_em", sa.DateTime(), nullable=True),
        sa.Column("motivo_devolucao", sa.Text(), nullable=True),
        sa.Column("lembrete_expiracao_em", sa.DateTime(), nullable=True),
        sa.Column("cancelado_em", sa.DateTime(), nullable=True),
        sa.Column("motivo_cancelamento", sa.Text(), nullable=True),
        sa.Column("ultima_movimentacao_em", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_solicitacoes_status", "solicitacoes", ["status"])
    op.create_index("ix_solicitacoes_solicitante", "solicitacoes", ["solicitante_email"])
    op.create_index("ix_solicitacoes_gestor", "solicitacoes", ["gestor_email"])

    op.create_table(
        "despesas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "solicitacao_id",
            sa.Integer(),
            sa.ForeignKey("solicitacoes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("categoria", sa.String(40), nullable=False),
        sa.Column("data_despesa", sa.Date(), nullable=False),
        sa.Column("valor", DINHEIRO, nullable=False),
        sa.Column("arquivo_chave", sa.String(300), nullable=False),
        sa.Column("arquivo_nome", sa.String(255), nullable=False),
        sa.Column("arquivo_tipo", sa.String(60), nullable=False),
        sa.Column("arquivo_tamanho", sa.Integer(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_despesas_solicitacao", "despesas", ["solicitacao_id"])

    op.create_table(
        "historico",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "solicitacao_id",
            sa.Integer(),
            sa.ForeignKey("solicitacoes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("acao", sa.String(40), nullable=False),
        sa.Column("status_de", sa.String(30), nullable=True),
        sa.Column("status_para", sa.String(30), nullable=False),
        sa.Column("usuario_email", sa.String(254), nullable=False),
        sa.Column("usuario_nome", sa.String(200), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_historico_solicitacao", "historico", ["solicitacao_id"])

    op.create_table(
        "notificacoes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "solicitacao_id",
            sa.Integer(),
            sa.ForeignKey("solicitacoes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("para", sa.Text(), nullable=False),
        sa.Column("assunto", sa.String(250), nullable=False),
        sa.Column("corpo", sa.Text(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("enviado_em", sa.DateTime(), nullable=True),
        sa.Column("erro", sa.Text(), nullable=True),
    )
    op.create_index("ix_notificacoes_pendentes", "notificacoes", ["enviado_em"])

    op.bulk_insert(centros, [{"codigo": c, "nome": n, "ativo": True} for c, n in CENTROS_CUSTO])
    op.bulk_insert(empresas, [{"nome": n, "ativo": True} for n in EMPRESAS])


def downgrade() -> None:
    for tabela in (
        "notificacoes",
        "historico",
        "despesas",
        "solicitacoes",
        "usuarios",
        "empresas",
        "centros_custo",
    ):
        op.drop_table(tabela)
