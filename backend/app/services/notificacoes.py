"""Avisos por e-mail a cada mudança de status (gravados na caixa de saída).

O envio de verdade entra quando a TI definir a conta de e-mail; até lá as
mensagens ficam na tabela `notificacoes` (nada se perde).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.papeis import FINANCEIRO
from app.auth.sessoes import agora_utc
from app.config import Settings
from app.models.cadastros import Usuario
from app.models.solicitacao import Notificacao, Solicitacao
from app.services.formatos import moeda


def emails_financeiro(db: Session) -> list[str]:
    usuarios = db.scalars(select(Usuario).where(Usuario.papeis.contains(FINANCEIRO))).all()
    return sorted(u.email for u in usuarios if FINANCEIRO in u.lista_papeis)


def enfileirar(
    db: Session,
    settings: Settings,
    sol: Solicitacao,
    para: list[str],
    titulo: str,
    texto: str,
) -> None:
    destinatarios = sorted({e.strip().lower() for e in para if e and e.strip()})
    if not destinatarios:
        return
    link = f"{settings.frontend_url}/solicitacoes/{sol.id}"
    corpo = (
        f"{texto}\n\n"
        f"Solicitação: {sol.codigo}\n"
        f"Solicitante: {sol.solicitante_nome}\n"
        f"Valor: {moeda(sol.valor_total, sol.moeda)}\n\n"
        f"Abrir no sistema: {link}\n"
    )
    db.add(
        Notificacao(
            solicitacao_id=sol.id,
            para=",".join(destinatarios),
            assunto=f"[Reembolso {sol.codigo}] {titulo}",
            corpo=corpo,
            criado_em=agora_utc(),
        )
    )
