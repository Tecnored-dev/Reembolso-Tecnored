"""Solicitação de reembolso, despesas (notas), histórico e caixa de saída de e-mails.

Uma `Solicitacao` serve para todos os tipos: "alimentacao" (uma nota) e
"viagem" (reembolso de viagem, várias notas) e "adiantamento" (diárias pagas
antes da viagem; depois, a prestação de contas com as notas).
Dados do solicitante que podem mudar com o tempo (matrícula, centro de custo,
empresa) são COPIADOS no envio, para o histórico não mudar
se a pessoa trocar de área.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

DINHEIRO = Numeric(12, 2)


class Solicitacao(Base):
    __tablename__ = "solicitacoes"

    @property
    def diaria_complementar(self) -> bool:
        return self.valor_complementar is not None

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)

    # Quem RECEBE o reembolso. Num pedido em nome de outra pessoa, é ela; quem
    # preencheu fica em `criado_por_*` (vazio quando a pessoa pediu para si).
    solicitante_email: Mapped[str] = mapped_column(String(254), nullable=False)
    solicitante_nome: Mapped[str] = mapped_column(String(200), nullable=False)
    criado_por_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    criado_por_nome: Mapped[str | None] = mapped_column(String(200), nullable=True)
    matricula: Mapped[str] = mapped_column(String(30), nullable=False)
    centro_custo: Mapped[str] = mapped_column(String(140), nullable=False)  # "3350 - T.I / T.A"
    empresa: Mapped[str] = mapped_column(String(120), nullable=False)

    gestor_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    gestor_nome: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Solicitante é gestor: pula a aprovação de gestor (regra de 06/10/2026).
    pula_gestor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    # Só em viagem: para onde e quando foi (a justificativa fica em `descricao`).
    destino: Mapped[str | None] = mapped_column(String(200), nullable=True)
    viagem_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    viagem_fim: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Só em adiantamento: quantas diárias foram pagas antes da viagem. O valor
    # adiantado fica em `valor_total`; o gasto comprovado, em `valor_gasto`.
    diarias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Diária complementar (quem recebe auxílio refeição): valor informado pelo
    # colaborador, somado às diárias normais (já incluído em `valor_total`).
    valor_complementar: Mapped[Decimal | None] = mapped_column(DINHEIRO, nullable=True)
    valor_gasto: Mapped[Decimal | None] = mapped_column(DINHEIRO, nullable=True)
    prestacao_enviada_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    prestacao_conferida_por: Mapped[str | None] = mapped_column(String(200), nullable=True)
    prestacao_conferida_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    devolucao_confirmada_por: Mapped[str | None] = mapped_column(String(200), nullable=True)
    devolucao_confirmada_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    diferenca_aprovada_por: Mapped[str | None] = mapped_column(String(200), nullable=True)
    diferenca_aprovada_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    data_pagamento_diferenca: Mapped[date | None] = mapped_column(Date, nullable=True)
    encerrado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lembrete_prestacao_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    aviso_prestacao_vencida_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    moeda: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    valor_total: Mapped[Decimal] = mapped_column(DINHEIRO, nullable=False)
    alerta_limite: Mapped[str | None] = mapped_column(Text, nullable=True)

    enviado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    conferido_por: Mapped[str | None] = mapped_column(String(200), nullable=True)
    conferido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    aprovado_por: Mapped[str | None] = mapped_column(String(200), nullable=True)
    aprovado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pago_por: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pago_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    data_pagamento: Mapped[date | None] = mapped_column(Date, nullable=True)

    devolvido_por: Mapped[str | None] = mapped_column(String(200), nullable=True)
    devolvido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    motivo_devolucao: Mapped[str | None] = mapped_column(Text, nullable=True)
    lembrete_expiracao_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    motivo_cancelamento: Mapped[str | None] = mapped_column(Text, nullable=True)

    ultima_movimentacao_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    despesas: Mapped[list[Despesa]] = relationship(
        back_populates="solicitacao",
        cascade="all, delete-orphan",
        order_by="Despesa.id",
        lazy="selectin",
    )
    historico: Mapped[list[Historico]] = relationship(
        back_populates="solicitacao",
        cascade="all, delete-orphan",
        order_by="Historico.id",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_solicitacoes_status", "status"),
        Index("ix_solicitacoes_solicitante", "solicitante_email"),
        Index("ix_solicitacoes_gestor", "gestor_email"),
        Index("ix_solicitacoes_criado_por", "criado_por_email"),
    )


class Despesa(Base):
    """Uma nota fiscal. Alimentação tem exatamente uma; viagem, uma ou mais.

    No adiantamento, as notas são as da prestação de contas, e o comprovante da
    transferência da sobra também fica aqui, com a categoria
    `comprovante_devolucao` (não entra na soma do gasto).
    """

    __tablename__ = "despesas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    solicitacao_id: Mapped[int] = mapped_column(
        ForeignKey("solicitacoes.id", ondelete="CASCADE"), nullable=False
    )
    categoria: Mapped[str] = mapped_column(String(40), nullable=False)
    data_despesa: Mapped[date] = mapped_column(Date, nullable=False)
    valor: Mapped[Decimal] = mapped_column(DINHEIRO, nullable=False)
    descricao: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Chave no armazenamento de arquivos (app/storage), nunca o arquivo em si.
    arquivo_chave: Mapped[str] = mapped_column(String(300), nullable=False)
    arquivo_nome: Mapped[str] = mapped_column(String(255), nullable=False)
    arquivo_tipo: Mapped[str] = mapped_column(String(60), nullable=False)
    arquivo_tamanho: Mapped[int] = mapped_column(Integer, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    solicitacao: Mapped[Solicitacao] = relationship(back_populates="despesas")

    __table_args__ = (Index("ix_despesas_solicitacao", "solicitacao_id"),)


class Historico(Base):
    """Quem fez o quê e quando — trilha de auditoria de cada solicitação."""

    __tablename__ = "historico"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    solicitacao_id: Mapped[int] = mapped_column(
        ForeignKey("solicitacoes.id", ondelete="CASCADE"), nullable=False
    )
    acao: Mapped[str] = mapped_column(String(40), nullable=False)
    status_de: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status_para: Mapped[str] = mapped_column(String(30), nullable=False)
    usuario_email: Mapped[str] = mapped_column(String(254), nullable=False)
    usuario_nome: Mapped[str] = mapped_column(String(200), nullable=False)
    comentario: Mapped[str | None] = mapped_column(Text, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    solicitacao: Mapped[Solicitacao] = relationship(back_populates="historico")

    __table_args__ = (Index("ix_historico_solicitacao", "solicitacao_id"),)


class Notificacao(Base):
    """Caixa de saída de e-mails.

    O sistema grava aqui a cada mudança de status; quem ENVIA é um passo
    separado, que entra quando a TI definir a conta/SMTP. Assim nenhum aviso
    se perde enquanto isso, e falha de e-mail nunca trava uma aprovação.
    """

    __tablename__ = "notificacoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    solicitacao_id: Mapped[int | None] = mapped_column(
        ForeignKey("solicitacoes.id", ondelete="SET NULL"), nullable=True
    )
    para: Mapped[str] = mapped_column(Text, nullable=False)  # e-mails separados por vírgula
    assunto: Mapped[str] = mapped_column(String(250), nullable=False)
    corpo: Mapped[str] = mapped_column(Text, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    erro: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_notificacoes_pendentes", "enviado_em"),)
