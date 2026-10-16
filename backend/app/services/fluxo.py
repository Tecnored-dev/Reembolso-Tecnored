"""Fluxo das solicitações: ALIMENTAÇÃO, VIAGEM e ADIANTAMENTO DE VIAGEM.

O reembolso de viagem (o colaborador pagou e pede depois, com as notas) segue
o MESMO fluxo da alimentação; a diferença é aceitar várias notas, cada uma com
categoria. O adiantamento de diárias tem fluxo próprio (fim deste texto).

Regras (Thais, 06/10/2026 — docs do projeto `fluxos-aprovacao.md`):

    colaborador envia ─▶ EM_CONFERENCIA (financeiro confere dados e nota)
        │ devolve ─▶ DEVOLVIDO ─(colaborador corrige e reenvia)─▶ EM_CONFERENCIA
        ▼ ok
    AGUARDANDO_GESTOR (o gestor escolhido aprova)      ← pulado se o solicitante é gestor
        │ recusa ─▶ RECUSADO (final: o colaborador abre um pedido novo — Thais, 15/10)
        ▼ aprova
    AGUARDANDO_PAGAMENTO ─(financeiro salva a data do pagamento)─▶ PAGO

- O gestor não devolve para correção: só aprova ou recusa (Thais, 15/10). Quem
  devolve para correção é o financeiro, na conferência.
- O centro de custo é escolhido em cada pedido (não é mais do perfil); o
  adiantamento não tem centro de custo (Thais, 15/10).

- Depois de enviar, o colaborador não edita nem cancela; só corrige quando devolvido.
- Devolvida e parada: lembrete 2 dias antes e cancelada depois de
  DIAS_EXPIRACAO_DEVOLVIDO dias (15, pedido da Thais em 09/10).
- Quem é do financeiro não confere o próprio pedido: outra pessoa do
  financeiro confere (Thais, 09/10).
- Alertas (não bloqueiam): refeição acima do limite diário (somando as notas
  do mesmo dia) e total acima do limite por solicitação.

Adiantamento (diárias = R$ 135 vezes os dias; regras de 06/10/2026):

    (diárias normais = R$ 135 por dia; ou diária complementar, com valor informado,
     para quem recebe auxílio refeição)
    colaborador pede ─▶ AGUARDANDO_GESTOR ─(aprova)─▶ AGUARDANDO_PAGAMENTO
        (pulado se o solicitante é gestor)    (Thais paga SEM conferir: não há nota)
        │ recusa ─▶ RECUSADO (final)
    pago ─▶ AGUARDANDO_PRESTACAO ─(colaborador manda as notas)─▶ PRESTACAO_EM_CONFERENCIA
        │ Thais devolve ─▶ PRESTACAO_DEVOLVIDA ─(corrige)─▶ PRESTACAO_EM_CONFERENCIA
        ▼ Thais confere (o resumo vai para a Thais e o gestor)
        ├─ sobrou ─▶ AGUARDANDO_DEVOLUCAO ─(comprovante da transferência)─▶
        │            DEVOLUCAO_EM_CONFERENCIA ─(Thais confirma)─▶ ENCERRADO
        │            (se recusar o comprovante, volta para AGUARDANDO_DEVOLUCAO)
        ├─ bateu ──▶ ENCERRADO
        └─ faltou ─▶ DIFERENCA_AGUARDANDO_GESTOR ─(aprova)─▶ DIFERENCA_AGUARDANDO_PAGAMENTO
                     (pulado se gestor)  │ recusa ─▶ RECUSADO (final, sem a diferença)
                                         ─(Thais paga a diferença)─▶ ENCERRADO

Prestação de contas: prazo de PRAZO_PRESTACAO_DIAS (60) depois da volta, com
lembrete antes e aviso quando vence (não bloqueia: o dinheiro já foi pago).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.papeis import ADMIN, FINANCEIRO, GESTOR
from app.auth.sessoes import Usuario, agora_utc
from app.config import (
    CATEGORIA_DESCRICAO_OBRIGATORIA,
    CATEGORIAS_VIAGEM,
    DIAS_EXPIRACAO_DEVOLVIDO,
    DIAS_LEMBRETE_DEVOLVIDO,
    DIAS_LEMBRETE_PRESTACAO,
    LIMITE_ALIMENTACAO_DIA,
    LIMITE_REFEICAO_DIA,
    LIMITE_SOLICITACAO,
    MAX_DESPESAS_VIAGEM,
    MAX_DIARIAS,
    MOTIVOS,
    PRAZO_PRESTACAO_DIAS,
    VALOR_DIARIA,
    Settings,
)
from app.models.cadastros import CentroCusto, Empresa
from app.models.cadastros import Usuario as CadastroUsuario
from app.models.solicitacao import Despesa, Historico, Solicitacao
from app.services import arquivos, gestores, notificacoes
from app.services.erros import NaoEncontrado, RegraNegocio, SemPermissao
from app.services.formatos import moeda
from app.storage import Armazenamento

log = logging.getLogger(__name__)

TIPO_ALIMENTACAO = "alimentacao"
# Despesas diversas (Nirlene, 13/10): tudo que não é alimentação, viagem nem
# adiantamento (ex.: carregador, créditos de celular). Mesmo fluxo da alimentação.
TIPO_DIVERSAS = "diversas"
TIPO_VIAGEM = "viagem"
TIPO_ADIANTAMENTO = "adiantamento"
ROTULO_TIPO = {
    TIPO_ALIMENTACAO: "Alimentação",
    TIPO_DIVERSAS: "Despesas diversas",
    TIPO_VIAGEM: "Viagem",
    TIPO_ADIANTAMENTO: "Adiantamento de viagem",
}
# "Reembolso de despesas - Prestação de Contas" (Thais, 15/10): alimentação ou
# despesas diversas, com uma ou mais notas. Na alimentação cada nota tem a
# categoria (lista das notas de viagem); nas diversas, todas são `diversos`.
TIPOS_DESPESAS = (TIPO_ALIMENTACAO, TIPO_DIVERSAS)
CATEGORIA_DIVERSAS = "diversos"
# Categorias que contam para o limite diário de refeição da alimentação (R$ 40).
CATEGORIAS_REFEICAO_ALIMENTACAO = ("refeicao", "almoco_pinda")
# Despesa especial do adiantamento: o comprovante da transferência da sobra.
COMPROVANTE_DEVOLUCAO = "comprovante_devolucao"

EM_CONFERENCIA = "em_conferencia"
AGUARDANDO_GESTOR = "aguardando_gestor"
AGUARDANDO_PAGAMENTO = "aguardando_pagamento"
PAGO = "pago"
DEVOLVIDO = "devolvido"
CANCELADO = "cancelado"
# Recusa do gestor: final (Thais, 15/10).
RECUSADO = "recusado"
# Só do adiantamento (depois do pagamento das diárias)
AGUARDANDO_PRESTACAO = "aguardando_prestacao"
PRESTACAO_EM_CONFERENCIA = "prestacao_em_conferencia"
PRESTACAO_DEVOLVIDA = "prestacao_devolvida"
AGUARDANDO_DEVOLUCAO = "aguardando_devolucao"
DEVOLUCAO_EM_CONFERENCIA = "devolucao_em_conferencia"
DIFERENCA_AGUARDANDO_GESTOR = "diferenca_aguardando_gestor"
DIFERENCA_AGUARDANDO_PAGAMENTO = "diferenca_aguardando_pagamento"
ENCERRADO = "encerrado"

ROTULO_STATUS = {
    EM_CONFERENCIA: "Pendente de conferência",
    AGUARDANDO_GESTOR: "Pendente de aprovação",
    AGUARDANDO_PAGAMENTO: "Aguardando pagamento",
    PAGO: "Finalizado - Pago",
    RECUSADO: "Finalizado - Recusado",
    DEVOLVIDO: "Devolvida para correção",
    CANCELADO: "Cancelada",
    AGUARDANDO_PRESTACAO: "Paga — aguardando prestação de contas",
    PRESTACAO_EM_CONFERENCIA: "Prestação de contas em conferência (financeiro)",
    PRESTACAO_DEVOLVIDA: "Prestação de contas devolvida para correção",
    AGUARDANDO_DEVOLUCAO: "Aguardando devolução da sobra",
    DEVOLUCAO_EM_CONFERENCIA: "Devolução enviada — aguardando confirmação",
    DIFERENCA_AGUARDANDO_GESTOR: "Diferença aguardando aprovação do gestor",
    DIFERENCA_AGUARDANDO_PAGAMENTO: "Diferença aprovada — aguardando pagamento",
    ENCERRADO: "Encerrada",
}

# Em que fila de trabalho cada status aparece.
FILA_CONFERENCIA = (EM_CONFERENCIA, PRESTACAO_EM_CONFERENCIA, DEVOLUCAO_EM_CONFERENCIA)
FILA_GESTOR = (AGUARDANDO_GESTOR, DIFERENCA_AGUARDANDO_GESTOR)
FILA_PAGAMENTO = (AGUARDANDO_PAGAMENTO, DIFERENCA_AGUARDANDO_PAGAMENTO)

OUTRO_FINANCEIRO = "Outra pessoa do financeiro precisa conferir o seu próprio pedido."

EMAIL_VALIDO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SISTEMA = Usuario(email="sistema", nome="Sistema", papeis=(), via="sistema")


@dataclass(frozen=True)
class Beneficiario:
    """Pedido em nome de outra pessoa (Thais, 13/10): qualquer colaborador pode
    pedir; o dinheiro vai para o beneficiário e quem aprova é o gestor dele.
    Nome e matrícula só são usados se o beneficiário ainda não tiver a
    matrícula no sistema (nunca entrou). O centro de custo é o do pedido."""

    email: str
    nome: str = ""
    matricula: str = ""


@dataclass(frozen=True)
class _Pessoa:
    """Quem recebe o reembolso (vira o "solicitante" da solicitação)."""

    email: str
    nome: str
    matricula: str
    eh_gestor: bool
    criado_por_email: str | None = None
    criado_por_nome: str | None = None


@dataclass(frozen=True)
class DadosDespesas:
    """Reembolso de despesas (alimentação ou diversas): uma ou mais notas."""

    descricao: str
    empresa_id: int
    gestor_email: str | None
    itens: tuple[ItemViagem, ...]
    beneficiario: Beneficiario | None = None
    motivo: str = ""
    # Escolhido no pedido. Obrigatório ao criar; na correção, None mantém o atual.
    centro_custo_id: int | None = None


@dataclass(frozen=True)
class ItemViagem:
    """Uma nota do reembolso de viagem.

    `id` existe só na correção, para manter uma nota já enviada. `arquivo` é a
    posição do arquivo na lista enviada junto (obrigatório em nota nova; na
    correção de uma nota existente, só quando a nota for trocada).
    """

    categoria: str
    data_despesa: date
    valor: Decimal
    descricao: str
    arquivo: int | None = None
    id: int | None = None


@dataclass(frozen=True)
class DadosAdiantamento:
    destino: str
    inicio: date
    fim: date
    descricao: str  # justificativa
    empresa_id: int
    gestor_email: str | None
    # Diária complementar (quem recebe auxílio refeição): valor informado pelo
    # colaborador, SOMADO às diárias normais (Thais, 13/10). None = sem complementar.
    complementar: Decimal | None = None
    beneficiario: Beneficiario | None = None


@dataclass(frozen=True)
class DadosViagem:
    destino: str
    inicio: date
    fim: date
    descricao: str  # justificativa
    empresa_id: int
    gestor_email: str | None
    itens: tuple[ItemViagem, ...]
    beneficiario: Beneficiario | None = None
    # Escolhido no pedido. Obrigatório ao criar; na correção, None mantém o atual.
    centro_custo_id: int | None = None


# ---------------------------------------------------------------------------
# Leitura e visibilidade
# ---------------------------------------------------------------------------
def eh_dono(sol: Solicitacao, usuario: Usuario) -> bool:
    """Quem recebe o reembolso ou quem criou o pedido em nome dele."""
    return usuario.email in (sol.solicitante_email, sol.criado_por_email)


def interessados(sol: Solicitacao) -> list[str]:
    """Quem recebe os avisos do colaborador: o beneficiário e quem criou o pedido."""
    return [e for e in (sol.solicitante_email, sol.criado_por_email) if e]


def pode_ver(sol: Solicitacao, usuario: Usuario) -> bool:
    return (
        eh_dono(sol, usuario)
        or sol.gestor_email == usuario.email
        or usuario.tem(FINANCEIRO)
        or usuario.tem(ADMIN)
    )


def obter(db: Session, usuario: Usuario, sol_id: int) -> Solicitacao:
    sol = db.get(Solicitacao, sol_id)
    if sol is None or not pode_ver(sol, usuario):
        raise NaoEncontrado()
    return sol


ESCOPOS = ("minhas", "conferencia", "aprovacao", "pagamento", "todas")


def listar(db: Session, usuario: Usuario, escopo: str) -> list[Solicitacao]:
    consulta = select(Solicitacao).order_by(Solicitacao.ultima_movimentacao_em.desc())
    if escopo == "minhas":
        consulta = consulta.where(
            or_(
                Solicitacao.solicitante_email == usuario.email,
                Solicitacao.criado_por_email == usuario.email,
            )
        )
    elif escopo == "conferencia":
        _exigir(usuario.tem(FINANCEIRO), "Só o financeiro confere.")
        consulta = consulta.where(Solicitacao.status.in_(FILA_CONFERENCIA))
    elif escopo == "aprovacao":
        _exigir(usuario.tem(GESTOR), "Só gestores aprovam.")
        consulta = consulta.where(
            Solicitacao.status.in_(FILA_GESTOR),
            Solicitacao.gestor_email == usuario.email,
        )
    elif escopo == "pagamento":
        _exigir(usuario.tem(FINANCEIRO), "Só o financeiro paga.")
        consulta = consulta.where(Solicitacao.status.in_(FILA_PAGAMENTO))
    elif escopo == "todas":
        if not (usuario.tem(FINANCEIRO) or usuario.tem(ADMIN)):
            # Gestor vê as que passaram por ele; colaborador, as próprias.
            consulta = consulta.where(
                or_(
                    Solicitacao.solicitante_email == usuario.email,
                    Solicitacao.criado_por_email == usuario.email,
                    Solicitacao.gestor_email == usuario.email,
                )
            )
    else:
        raise RegraNegocio(f"Escopo inválido: {escopo}")
    return list(db.scalars(consulta).all())


def acoes_disponiveis(sol: Solicitacao, usuario: Usuario) -> list[str]:
    acoes = []
    dono = eh_dono(sol, usuario)
    financeiro = usuario.tem(FINANCEIRO)
    # Quem é do financeiro não confere o próprio pedido (outra pessoa confere).
    confere = financeiro and not dono
    if sol.status in (EM_CONFERENCIA, PRESTACAO_EM_CONFERENCIA) and confere:
        acoes += ["conferir", "devolver"]
    if sol.status in FILA_GESTOR and usuario.tem(GESTOR) and sol.gestor_email == usuario.email:
        acoes += ["aprovar", "recusar"]
    if sol.status in FILA_PAGAMENTO and financeiro:
        acoes.append("pagar")
    if sol.status == DEVOLVIDO and dono:
        acoes.append("reenviar")
    if sol.status in (AGUARDANDO_PRESTACAO, PRESTACAO_DEVOLVIDA) and dono:
        acoes.append("prestar_contas")
    if sol.status == AGUARDANDO_DEVOLUCAO and dono:
        acoes.append("enviar_comprovante")
    if sol.status == DEVOLUCAO_EM_CONFERENCIA and confere:
        acoes += ["confirmar_devolucao", "recusar_comprovante"]
    return acoes


def saldo(sol: Solicitacao) -> Decimal | None:
    """Adiantamento: positivo = sobrou (devolver); negativo = falta (reembolsar)."""
    if sol.tipo != TIPO_ADIANTAMENTO or sol.valor_gasto is None:
        return None
    return sol.valor_total - sol.valor_gasto


def prazo_prestacao(sol: Solicitacao) -> date | None:
    """Data limite da prestação de contas do adiantamento (60 dias após a volta)."""
    if sol.tipo != TIPO_ADIANTAMENTO or sol.viagem_fim is None:
        return None
    return sol.viagem_fim + timedelta(days=PRAZO_PRESTACAO_DIAS)


def calcular_diarias(inicio: date, fim: date) -> int:
    """Dias corridos contando ida e volta (SUPOSIÇÃO — confirmar com a Thais)."""
    return (fim - inicio).days + 1


# ---------------------------------------------------------------------------
# Criação e reenvio
# ---------------------------------------------------------------------------
def criar_alimentacao(
    db: Session,
    settings: Settings,
    armazenamento: Armazenamento,
    usuario: Usuario,
    dados: DadosDespesas,
    arquivos_enviados: list[arquivos.ArquivoValidado],
    tipo: str = TIPO_ALIMENTACAO,
) -> Solicitacao:
    """Reembolso de despesas - Prestação de Contas (Thais, 15/10): alimentação
    ou despesas diversas, com uma ou mais notas, mesmo fluxo."""
    if tipo not in TIPOS_DESPESAS:
        raise RegraNegocio("Tipo de solicitação inválido.")
    dados = _normalizar_despesas(dados, tipo)
    pessoa = _pessoa_do_pedido(db, settings, usuario, dados.beneficiario)
    # Na criação nenhuma nota existe ainda: qualquer `id` é recusado.
    _validar_despesas(dados, tipo, arquivos_enviados, existentes=set())

    agora = agora_utc()
    pula_gestor = pessoa.eh_gestor
    gestor = (
        None
        if pula_gestor
        else _validar_gestor(
            db, settings, pessoa.email, pessoa.criado_por_email, dados.gestor_email
        )
    )
    empresa = _empresa(db, dados.empresa_id)
    centro = _centro_custo(db, dados.centro_custo_id)

    sol = Solicitacao(
        tipo=tipo,
        status=EM_CONFERENCIA,
        solicitante_email=pessoa.email,
        solicitante_nome=pessoa.nome,
        criado_por_email=pessoa.criado_por_email,
        criado_por_nome=pessoa.criado_por_nome,
        matricula=pessoa.matricula,
        centro_custo=centro.rotulo,
        empresa=empresa.nome,
        gestor_email=gestor.email if gestor else None,
        gestor_nome=gestor.nome if gestor else None,
        pula_gestor=pula_gestor,
        descricao=dados.descricao.strip(),
        motivo=dados.motivo,
        valor_total=_total(dados.itens),
        alerta_limite=_alerta_despesas(dados.itens, tipo),
        enviado_em=agora,
        ultima_movimentacao_em=agora,
    )
    db.add(sol)
    db.flush()  # gera o id
    sol.codigo = f"REE-{sol.id:06d}"

    salvas: list[str] = []
    try:
        for item in dados.itens:
            arquivo = arquivos_enviados[item.arquivo or 0]
            chave = arquivos.salvar(armazenamento, arquivo, sol.codigo, agora)
            salvas.append(chave)
            sol.despesas.append(_despesa_viagem(item, arquivo, chave, agora))
        _registrar(db, sol, "enviado", None, EM_CONFERENCIA, usuario, None, agora)
        _lembrar_centro_custo(db, usuario, centro)
        notificacoes.enfileirar(
            db,
            settings,
            sol,
            notificacoes.emails_financeiro(db),
            "Nova solicitação para conferir",
            f"{_autor(usuario, sol)} enviou um reembolso de "
            f"{ROTULO_TIPO[tipo].lower()} para conferência.",
        )
        db.commit()
    except Exception:
        db.rollback()
        for chave in salvas:
            armazenamento.remover(chave)
        raise
    return sol


def reenviar(
    db: Session,
    settings: Settings,
    armazenamento: Armazenamento,
    usuario: Usuario,
    sol_id: int,
    dados: DadosDespesas,
    arquivos_enviados: list[arquivos.ArquivoValidado],
) -> Solicitacao:
    """Correção de um reembolso de despesas devolvido. A lista de notas enviada
    substitui a anterior (como na viagem): com `id` mantém, sem `id` é nova, e as
    que não vierem saem. Vale também para pedidos antigos, de uma nota só."""
    sol = obter(db, usuario, sol_id)
    _exigir(eh_dono(sol, usuario), "Só quem pediu pode corrigir.")
    _exigir_status(sol, DEVOLVIDO)
    if sol.tipo not in TIPOS_DESPESAS:
        raise RegraNegocio("Esta solicitação não é de alimentação (nem de despesas diversas).")
    dados = _normalizar_despesas(dados, sol.tipo)
    atuais = {d.id: d for d in sol.despesas}
    _validar_despesas(dados, sol.tipo, arquivos_enviados, existentes=set(atuais))
    if not sol.pula_gestor:
        gestor = _validar_gestor(
            db, settings, sol.solicitante_email, sol.criado_por_email, dados.gestor_email
        )
        sol.gestor_email, sol.gestor_nome = gestor.email, gestor.nome
    sol.empresa = _empresa(db, dados.empresa_id).nome
    if dados.centro_custo_id is not None:
        sol.centro_custo = _centro_custo(db, dados.centro_custo_id).rotulo
    sol.descricao = dados.descricao.strip()
    sol.motivo = dados.motivo
    sol.local_refeicao = None  # o local saiu do formulário (Thais, 15/10)
    sol.valor_total = _total(dados.itens)
    sol.alerta_limite = _alerta_despesas(dados.itens, sol.tipo)

    agora = agora_utc()
    novas_chaves: list[str] = []
    chaves_antigas: list[str] = []
    try:
        _sincronizar_notas(
            sol,
            atuais,
            dados.itens,
            arquivos_enviados,
            armazenamento,
            agora,
            novas_chaves,
            chaves_antigas,
        )
        sol.motivo_devolucao = None
        sol.devolvido_por = sol.devolvido_em = sol.lembrete_expiracao_em = None
        _mudar(db, sol, EM_CONFERENCIA, "reenviado", usuario, None, agora)
        notificacoes.enfileirar(
            db,
            settings,
            sol,
            notificacoes.emails_financeiro(db),
            "Solicitação corrigida para conferir",
            f"{usuario.nome} corrigiu e reenviou a solicitação.",
        )
        db.commit()
    except Exception:
        db.rollback()
        for chave in novas_chaves:
            armazenamento.remover(chave)
        raise
    for chave in chaves_antigas:
        armazenamento.remover(chave)
    return sol


def _normalizar_despesas(dados: DadosDespesas, tipo: str) -> DadosDespesas:
    """Despesas diversas não têm categoria por nota: todas viram `diversos`."""
    if tipo != TIPO_DIVERSAS:
        return dados
    return replace(
        dados, itens=tuple(replace(i, categoria=CATEGORIA_DIVERSAS) for i in dados.itens)
    )


def _validar_despesas(
    dados: DadosDespesas,
    tipo: str,
    arquivos_enviados: list[arquivos.ArquivoValidado],
    existentes: set[int],
) -> None:
    if dados.motivo not in MOTIVOS:
        raise RegraNegocio("Escolha o motivo da despesa.")
    if not dados.descricao.strip():
        raise RegraNegocio("Descreva a despesa.")
    if len(dados.descricao) > 500:
        raise RegraNegocio("Descrição muito longa (máximo 500 caracteres).")
    categorias = CATEGORIAS_VIAGEM if tipo == TIPO_ALIMENTACAO else {CATEGORIA_DIVERSAS: ""}
    _validar_itens(dados.itens, arquivos_enviados, existentes, categorias)


def _alerta_despesas(itens: tuple[ItemViagem, ...], tipo: str) -> str | None:
    """Só avisa (não bloqueia). Alimentação: refeição acima de R$ 40 no dia,
    somando as notas do mesmo dia (Thais, 15/10). Os dois tipos: total acima
    do limite por solicitação."""
    alertas = []
    if tipo == TIPO_ALIMENTACAO:
        por_dia: dict[date, Decimal] = {}
        for item in itens:
            if item.categoria in CATEGORIAS_REFEICAO_ALIMENTACAO:
                dia = item.data_despesa
                por_dia[dia] = por_dia.get(dia, Decimal("0")) + item.valor
        dias = sorted(d for d, v in por_dia.items() if v > LIMITE_ALIMENTACAO_DIA)
        if dias:
            lista = ", ".join(f"{d:%d/%m}" for d in dias)
            alertas.append(
                f"Refeição acima do limite da política ({moeda(LIMITE_ALIMENTACAO_DIA)} "
                f"por dia) em {lista}."
            )
    if _total(itens) > LIMITE_SOLICITACAO:
        alertas.append(f"Total acima do limite por solicitação ({moeda(LIMITE_SOLICITACAO)}).")
    return " ".join(alertas) or None


# ---------------------------------------------------------------------------
# Reembolso de viagem (várias notas)
# ---------------------------------------------------------------------------
def criar_viagem(
    db: Session,
    settings: Settings,
    armazenamento: Armazenamento,
    usuario: Usuario,
    dados: DadosViagem,
    arquivos_enviados: list[arquivos.ArquivoValidado],
) -> Solicitacao:
    pessoa = _pessoa_do_pedido(db, settings, usuario, dados.beneficiario)
    # Na criação nenhuma nota existe ainda: qualquer `id` é recusado.
    _validar_viagem(dados, arquivos_enviados, existentes=set())

    agora = agora_utc()
    pula_gestor = pessoa.eh_gestor
    gestor = (
        None
        if pula_gestor
        else _validar_gestor(
            db, settings, pessoa.email, pessoa.criado_por_email, dados.gestor_email
        )
    )
    empresa = _empresa(db, dados.empresa_id)
    centro = _centro_custo(db, dados.centro_custo_id)

    sol = Solicitacao(
        tipo=TIPO_VIAGEM,
        status=EM_CONFERENCIA,
        solicitante_email=pessoa.email,
        solicitante_nome=pessoa.nome,
        criado_por_email=pessoa.criado_por_email,
        criado_por_nome=pessoa.criado_por_nome,
        matricula=pessoa.matricula,
        centro_custo=centro.rotulo,
        empresa=empresa.nome,
        gestor_email=gestor.email if gestor else None,
        gestor_nome=gestor.nome if gestor else None,
        pula_gestor=pula_gestor,
        descricao=dados.descricao.strip(),
        destino=dados.destino.strip(),
        viagem_inicio=dados.inicio,
        viagem_fim=dados.fim,
        valor_total=_total(dados.itens),
        alerta_limite=_alerta_viagem(dados.itens),
        enviado_em=agora,
        ultima_movimentacao_em=agora,
    )
    db.add(sol)
    db.flush()
    sol.codigo = f"REE-{sol.id:06d}"

    salvas: list[str] = []
    try:
        for item in dados.itens:
            arquivo = arquivos_enviados[item.arquivo or 0]
            chave = arquivos.salvar(armazenamento, arquivo, sol.codigo, agora)
            salvas.append(chave)
            sol.despesas.append(_despesa_viagem(item, arquivo, chave, agora))
        _registrar(db, sol, "enviado", None, EM_CONFERENCIA, usuario, None, agora)
        _lembrar_centro_custo(db, usuario, centro)
        notificacoes.enfileirar(
            db,
            settings,
            sol,
            notificacoes.emails_financeiro(db),
            "Nova solicitação para conferir",
            f"{_autor(usuario, sol)} enviou um reembolso de viagem ({dados.destino.strip()}) "
            "para conferência.",
        )
        db.commit()
    except Exception:
        db.rollback()
        for chave in salvas:
            armazenamento.remover(chave)
        raise
    return sol


def reenviar_viagem(
    db: Session,
    settings: Settings,
    armazenamento: Armazenamento,
    usuario: Usuario,
    sol_id: int,
    dados: DadosViagem,
    arquivos_enviados: list[arquivos.ArquivoValidado],
) -> Solicitacao:
    """Correção de um reembolso de viagem devolvido.

    A lista enviada substitui a anterior: notas com `id` são mantidas (e
    atualizadas), notas sem `id` são novas, e as que não vierem são removidas.
    """
    sol = obter(db, usuario, sol_id)
    _exigir(eh_dono(sol, usuario), "Só quem pediu pode corrigir.")
    _exigir_status(sol, DEVOLVIDO)
    if sol.tipo != TIPO_VIAGEM:
        raise RegraNegocio("Esta solicitação não é de viagem.")
    atuais = {d.id: d for d in sol.despesas}
    _validar_viagem(dados, arquivos_enviados, existentes=set(atuais))
    if not sol.pula_gestor:
        gestor = _validar_gestor(
            db, settings, sol.solicitante_email, sol.criado_por_email, dados.gestor_email
        )
        sol.gestor_email, sol.gestor_nome = gestor.email, gestor.nome
    sol.empresa = _empresa(db, dados.empresa_id).nome
    if dados.centro_custo_id is not None:
        sol.centro_custo = _centro_custo(db, dados.centro_custo_id).rotulo
    sol.descricao = dados.descricao.strip()
    sol.destino = dados.destino.strip()
    sol.viagem_inicio, sol.viagem_fim = dados.inicio, dados.fim
    sol.valor_total = _total(dados.itens)
    sol.alerta_limite = _alerta_viagem(dados.itens)

    agora = agora_utc()
    novas_chaves: list[str] = []
    chaves_antigas: list[str] = []
    try:
        _sincronizar_notas(
            sol,
            atuais,
            dados.itens,
            arquivos_enviados,
            armazenamento,
            agora,
            novas_chaves,
            chaves_antigas,
        )
        sol.motivo_devolucao = None
        sol.devolvido_por = sol.devolvido_em = sol.lembrete_expiracao_em = None
        _mudar(db, sol, EM_CONFERENCIA, "reenviado", usuario, None, agora)
        notificacoes.enfileirar(
            db,
            settings,
            sol,
            notificacoes.emails_financeiro(db),
            "Solicitação corrigida para conferir",
            f"{usuario.nome} corrigiu e reenviou a solicitação.",
        )
        db.commit()
    except Exception:
        db.rollback()
        for chave in novas_chaves:
            armazenamento.remover(chave)
        raise
    for chave in chaves_antigas:
        armazenamento.remover(chave)
    return sol


def _sincronizar_notas(
    sol: Solicitacao,
    atuais: dict[int, Despesa],
    itens: tuple[ItemViagem, ...],
    arquivos_enviados: list[arquivos.ArquivoValidado],
    armazenamento: Armazenamento,
    agora: datetime,
    novas_chaves: list[str],
    chaves_antigas: list[str],
) -> None:
    """A lista enviada substitui `atuais`: com `id` mantém (e atualiza), sem `id`
    é nota nova, e as que não vierem saem. Anota as chaves de arquivo gravadas
    (para apagar se der erro) e as que deixaram de ser usadas (para apagar
    depois do commit)."""
    mantidas = {item.id for item in itens if item.id is not None}
    for despesa_id, despesa in atuais.items():
        if despesa_id not in mantidas:
            chaves_antigas.append(despesa.arquivo_chave)
            sol.despesas.remove(despesa)
    for item in itens:
        arquivo = arquivos_enviados[item.arquivo] if item.arquivo is not None else None
        chave = None
        if arquivo is not None:
            chave = arquivos.salvar(armazenamento, arquivo, sol.codigo or "", agora)
            novas_chaves.append(chave)
        if item.id is None:
            assert arquivo is not None and chave is not None  # garantido na validação
            sol.despesas.append(_despesa_viagem(item, arquivo, chave, agora))
            continue
        despesa = atuais[item.id]
        despesa.categoria, despesa.data_despesa = item.categoria, item.data_despesa
        despesa.valor, despesa.descricao = item.valor, item.descricao.strip() or None
        if arquivo is not None and chave is not None:
            chaves_antigas.append(despesa.arquivo_chave)
            despesa.arquivo_chave = chave
            despesa.arquivo_nome, despesa.arquivo_tipo = arquivo.nome, arquivo.tipo
            despesa.arquivo_tamanho = len(arquivo.conteudo)


def _validar_viagem(
    dados: DadosViagem, arquivos_enviados: list[arquivos.ArquivoValidado], existentes: set[int]
) -> None:
    if not dados.destino.strip():
        raise RegraNegocio("Informe o destino da viagem.")
    if len(dados.destino) > 200:
        raise RegraNegocio("Destino muito longo (máximo 200 caracteres).")
    if dados.fim < dados.inicio:
        raise RegraNegocio("O fim da viagem não pode ser antes do início.")
    if not dados.descricao.strip():
        raise RegraNegocio("Explique o motivo da viagem.")
    if len(dados.descricao) > 500:
        raise RegraNegocio("Justificativa muito longa (máximo 500 caracteres).")
    _validar_itens(dados.itens, arquivos_enviados, existentes)


def _validar_itens(
    itens: tuple[ItemViagem, ...],
    arquivos_enviados: list[arquivos.ArquivoValidado],
    existentes: set[int],
    categorias: dict[str, str] = CATEGORIAS_VIAGEM,
) -> None:
    """Notas: viagem, prestação de contas do adiantamento e reembolso de despesas."""
    hoje = date.today()
    if not itens:
        raise RegraNegocio("Inclua pelo menos uma nota.")
    if len(itens) > MAX_DESPESAS_VIAGEM:
        raise RegraNegocio(f"Máximo de {MAX_DESPESAS_VIAGEM} notas por solicitação.")

    usados: set[int] = set()
    ids: set[int] = set()
    for n, item in enumerate(itens, start=1):
        if item.categoria not in categorias:
            raise RegraNegocio(f"Nota {n}: categoria inválida.")
        if item.data_despesa > hoje:
            raise RegraNegocio(f"Nota {n}: a data não pode ser no futuro.")
        if len(item.descricao) > 200:
            raise RegraNegocio(f"Nota {n}: descrição muito longa (máximo 200 caracteres).")
        if item.categoria == CATEGORIA_DESCRICAO_OBRIGATORIA and not item.descricao.strip():
            rotulo = CATEGORIAS_VIAGEM[CATEGORIA_DESCRICAO_OBRIGATORIA]
            raise RegraNegocio(f"Nota {n}: descreva a despesa ({rotulo}).")
        if item.id is not None:
            if item.id not in existentes or item.id in ids:
                raise RegraNegocio(f"Nota {n}: nota inválida.")
            ids.add(item.id)
        elif item.arquivo is None:
            raise RegraNegocio(f"Nota {n}: anexe a foto ou o PDF.")
        if item.arquivo is not None:
            if not 0 <= item.arquivo < len(arquivos_enviados) or item.arquivo in usados:
                raise RegraNegocio(f"Nota {n}: arquivo inválido.")
            usados.add(item.arquivo)


def _total(itens: tuple[ItemViagem, ...]) -> Decimal:
    return sum((item.valor for item in itens), Decimal("0.00"))


def _alerta_viagem(itens: tuple[ItemViagem, ...]) -> str | None:
    alertas = []
    por_dia: dict[date, Decimal] = {}
    for item in itens:
        if item.categoria == "refeicao":
            por_dia[item.data_despesa] = por_dia.get(item.data_despesa, Decimal("0")) + item.valor
    dias = sorted(d for d, v in por_dia.items() if v > LIMITE_REFEICAO_DIA)
    if dias:
        lista = ", ".join(f"{d:%d/%m}" for d in dias)
        alertas.append(
            f"Refeição acima do limite diário da política ({moeda(LIMITE_REFEICAO_DIA)}) "
            f"em {lista}."
        )
    total = _total(itens)
    if total > LIMITE_SOLICITACAO:
        alertas.append(f"Total acima do limite por solicitação ({moeda(LIMITE_SOLICITACAO)}).")
    return " ".join(alertas) or None


def _despesa_viagem(
    item: ItemViagem, arquivo: arquivos.ArquivoValidado, chave: str, agora: datetime
) -> Despesa:
    return Despesa(
        categoria=item.categoria,
        data_despesa=item.data_despesa,
        valor=item.valor,
        descricao=item.descricao.strip() or None,
        arquivo_chave=chave,
        arquivo_nome=arquivo.nome,
        arquivo_tipo=arquivo.tipo,
        arquivo_tamanho=len(arquivo.conteudo),
        criado_em=agora,
    )


# ---------------------------------------------------------------------------
# Adiantamento de viagem (diárias pagas antes; prestação de contas depois)
# ---------------------------------------------------------------------------
def criar_adiantamento(
    db: Session,
    settings: Settings,
    usuario: Usuario,
    dados: DadosAdiantamento,
) -> Solicitacao:
    pessoa = _pessoa_do_pedido(db, settings, usuario, dados.beneficiario)
    diarias = _validar_adiantamento(dados)

    agora = agora_utc()
    pula_gestor = pessoa.eh_gestor
    gestor = (
        None
        if pula_gestor
        else _validar_gestor(
            db, settings, pessoa.email, pessoa.criado_por_email, dados.gestor_email
        )
    )
    empresa = _empresa(db, dados.empresa_id)
    valor = _valor_adiantamento(dados, diarias)
    status = AGUARDANDO_PAGAMENTO if pula_gestor else AGUARDANDO_GESTOR

    sol = Solicitacao(
        tipo=TIPO_ADIANTAMENTO,
        status=status,
        solicitante_email=pessoa.email,
        solicitante_nome=pessoa.nome,
        criado_por_email=pessoa.criado_por_email,
        criado_por_nome=pessoa.criado_por_nome,
        matricula=pessoa.matricula,
        centro_custo=None,  # adiantamento não tem centro de custo (Thais, 15/10)
        empresa=empresa.nome,
        gestor_email=gestor.email if gestor else None,
        gestor_nome=gestor.nome if gestor else None,
        pula_gestor=pula_gestor,
        descricao=dados.descricao.strip(),
        destino=dados.destino.strip(),
        viagem_inicio=dados.inicio,
        viagem_fim=dados.fim,
        diarias=diarias,
        valor_complementar=dados.complementar,
        valor_total=valor,
        alerta_limite=_alerta_total(valor),
        enviado_em=agora,
        ultima_movimentacao_em=agora,
    )
    db.add(sol)
    db.flush()
    sol.codigo = f"REE-{sol.id:06d}"
    _registrar(db, sol, "enviado", None, status, usuario, None, agora)
    _avisar_pedido_adiantamento(db, settings, sol, f"{_autor(usuario, sol)} pediu")
    db.commit()
    return sol


def reenviar_adiantamento(
    db: Session,
    settings: Settings,
    usuario: Usuario,
    sol_id: int,
    dados: DadosAdiantamento,
) -> Solicitacao:
    """Correção de um pedido devolvido antes de 15/10 (o gestor devolvia).

    Hoje o gestor só aprova ou recusa; fica para os pedidos antigos."""
    sol = obter(db, usuario, sol_id)
    _exigir(eh_dono(sol, usuario), "Só quem pediu pode corrigir.")
    _exigir_status(sol, DEVOLVIDO)
    if sol.tipo != TIPO_ADIANTAMENTO:
        raise RegraNegocio("Esta solicitação não é de adiantamento.")
    diarias = _validar_adiantamento(dados)
    if not sol.pula_gestor:
        gestor = _validar_gestor(
            db, settings, sol.solicitante_email, sol.criado_por_email, dados.gestor_email
        )
        sol.gestor_email, sol.gestor_nome = gestor.email, gestor.nome
    sol.empresa = _empresa(db, dados.empresa_id).nome
    sol.descricao = dados.descricao.strip()
    sol.destino = dados.destino.strip()
    sol.viagem_inicio, sol.viagem_fim = dados.inicio, dados.fim
    sol.diarias = diarias
    sol.valor_complementar = dados.complementar
    sol.valor_total = _valor_adiantamento(dados, diarias)
    sol.alerta_limite = _alerta_total(sol.valor_total)

    agora = agora_utc()
    sol.motivo_devolucao = None
    sol.devolvido_por = sol.devolvido_em = sol.lembrete_expiracao_em = None
    novo = AGUARDANDO_PAGAMENTO if sol.pula_gestor else AGUARDANDO_GESTOR
    _mudar(db, sol, novo, "reenviado", usuario, None, agora)
    _avisar_pedido_adiantamento(db, settings, sol, f"{usuario.nome} corrigiu e reenviou")
    db.commit()
    return sol


def enviar_prestacao(
    db: Session,
    settings: Settings,
    armazenamento: Armazenamento,
    usuario: Usuario,
    sol_id: int,
    itens: tuple[ItemViagem, ...],
    arquivos_enviados: list[arquivos.ArquivoValidado],
) -> Solicitacao:
    """Prestação de contas (primeira vez ou correção): as notas do que foi gasto.

    Na correção vale a mesma regra do reembolso de viagem: notas com `id` são
    mantidas, sem `id` são novas, e as que não vierem são removidas.
    """
    sol = obter(db, usuario, sol_id)
    _exigir(eh_dono(sol, usuario), "Só quem pediu presta contas.")
    if sol.tipo != TIPO_ADIANTAMENTO:
        raise RegraNegocio("Esta solicitação não é de adiantamento.")
    if sol.status not in (AGUARDANDO_PRESTACAO, PRESTACAO_DEVOLVIDA):
        _exigir_status(sol, AGUARDANDO_PRESTACAO)
    atuais = {d.id: d for d in sol.despesas if d.categoria != COMPROVANTE_DEVOLUCAO}
    _validar_itens(itens, arquivos_enviados, existentes=set(atuais))

    agora = agora_utc()
    primeira = sol.status == AGUARDANDO_PRESTACAO
    novas_chaves: list[str] = []
    chaves_antigas: list[str] = []
    try:
        _sincronizar_notas(
            sol,
            atuais,
            itens,
            arquivos_enviados,
            armazenamento,
            agora,
            novas_chaves,
            chaves_antigas,
        )
        sol.valor_gasto = _total(itens)
        sol.alerta_limite = _alerta_viagem(itens)
        sol.prestacao_enviada_em = agora
        sol.motivo_devolucao = None
        sol.devolvido_por = sol.devolvido_em = None
        acao = "prestacao_enviada" if primeira else "prestacao_reenviada"
        _mudar(db, sol, PRESTACAO_EM_CONFERENCIA, acao, usuario, None, agora)
        notificacoes.enfileirar(
            db,
            settings,
            sol,
            notificacoes.emails_financeiro(db),
            "Prestação de contas para conferir",
            f"{usuario.nome} {'enviou' if primeira else 'corrigiu e reenviou'} a prestação "
            f"de contas do adiantamento: gasto de {moeda(sol.valor_gasto)}.",
        )
        db.commit()
    except Exception:
        db.rollback()
        for chave in novas_chaves:
            armazenamento.remover(chave)
        raise
    for chave in chaves_antigas:
        armazenamento.remover(chave)
    return sol


def enviar_comprovante(
    db: Session,
    settings: Settings,
    armazenamento: Armazenamento,
    usuario: Usuario,
    sol_id: int,
    data_transferencia: date,
    arquivo: arquivos.ArquivoValidado,
) -> Solicitacao:
    """Comprovante da transferência da sobra (os dados bancários a Thais passa por fora)."""
    sol = obter(db, usuario, sol_id)
    _exigir(eh_dono(sol, usuario), "Só quem pediu envia o comprovante.")
    _exigir_status(sol, AGUARDANDO_DEVOLUCAO)
    if data_transferencia > date.today():
        raise RegraNegocio("A data da transferência não pode ser no futuro.")
    sobra = saldo(sol) or Decimal("0.00")

    agora = agora_utc()
    anteriores = [d for d in sol.despesas if d.categoria == COMPROVANTE_DEVOLUCAO]
    chave = arquivos.salvar(armazenamento, arquivo, sol.codigo or "", agora)
    try:
        for antigo in anteriores:
            sol.despesas.remove(antigo)
        sol.despesas.append(
            Despesa(
                categoria=COMPROVANTE_DEVOLUCAO,
                data_despesa=data_transferencia,
                valor=sobra,
                descricao="Comprovante da devolução",
                arquivo_chave=chave,
                arquivo_nome=arquivo.nome,
                arquivo_tipo=arquivo.tipo,
                arquivo_tamanho=len(arquivo.conteudo),
                criado_em=agora,
            )
        )
        sol.motivo_devolucao = None
        sol.devolvido_por = sol.devolvido_em = None
        _mudar(
            db,
            sol,
            DEVOLUCAO_EM_CONFERENCIA,
            "comprovante_enviado",
            usuario,
            f"Transferência em {data_transferencia:%d/%m/%Y}",
            agora,
        )
        notificacoes.enfileirar(
            db,
            settings,
            sol,
            notificacoes.emails_financeiro(db),
            "Devolução de adiantamento para confirmar",
            f"{usuario.nome} enviou o comprovante da devolução de {moeda(sobra)}. "
            "Confirme quando o valor cair na conta.",
        )
        db.commit()
    except Exception:
        db.rollback()
        armazenamento.remover(chave)
        raise
    for antigo in anteriores:
        armazenamento.remover(antigo.arquivo_chave)
    return sol


def confirmar_devolucao(
    db: Session,
    settings: Settings,
    usuario: Usuario,
    sol_id: int,
    aprovar: bool,
    comentario: str | None,
) -> Solicitacao:
    """A Thais confirma que a sobra caiu na conta (encerra) ou recusa o comprovante."""
    sol = obter(db, usuario, sol_id)
    _exigir(usuario.tem(FINANCEIRO), "Só o financeiro confirma a devolução.")
    _exigir(not eh_dono(sol, usuario), OUTRO_FINANCEIRO)
    _exigir_status(sol, DEVOLUCAO_EM_CONFERENCIA)
    agora = agora_utc()
    if not aprovar:
        motivo = (comentario or "").strip()
        if not motivo:
            raise RegraNegocio("Explique o que há de errado com o comprovante.")
        sol.devolvido_por, sol.devolvido_em, sol.motivo_devolucao = usuario.nome, agora, motivo
        _mudar(db, sol, AGUARDANDO_DEVOLUCAO, "comprovante_recusado", usuario, motivo, agora)
        notificacoes.enfileirar(
            db,
            settings,
            sol,
            interessados(sol),
            "Comprovante de devolução recusado",
            f"{usuario.nome} recusou o comprovante: {motivo}",
        )
        db.commit()
        return sol

    sol.devolucao_confirmada_por, sol.devolucao_confirmada_em = usuario.nome, agora
    _encerrar(db, sol, "devolucao_confirmada", usuario, comentario, agora)
    notificacoes.enfileirar(
        db,
        settings,
        sol,
        interessados(sol),
        "Adiantamento encerrado",
        "O financeiro confirmou o recebimento da devolução. O adiantamento está encerrado.",
    )
    db.commit()
    return sol


def _conferir_prestacao(
    db: Session,
    settings: Settings,
    sol: Solicitacao,
    usuario: Usuario,
    aprovar: bool,
    comentario: str | None,
) -> Solicitacao:
    agora = agora_utc()
    if not aprovar:
        return _devolver(db, settings, sol, usuario, comentario, agora, para=PRESTACAO_DEVOLVIDA)

    sol.prestacao_conferida_por, sol.prestacao_conferida_em = usuario.nome, agora
    diferenca = saldo(sol) or Decimal("0.00")
    if diferenca > 0:
        _mudar(db, sol, AGUARDANDO_DEVOLUCAO, "prestacao_conferida", usuario, comentario, agora)
        texto = (
            f"A prestação de contas foi conferida. Sobrou {moeda(diferenca)}: faça a "
            "transferência (o financeiro passa os dados bancários) e anexe o comprovante."
        )
    elif diferenca == 0:
        _encerrar(db, sol, "prestacao_conferida", usuario, comentario, agora)
        texto = "A prestação de contas foi conferida e bateu com o adiantamento. Encerrada."
    elif sol.pula_gestor:
        _mudar(
            db,
            sol,
            DIFERENCA_AGUARDANDO_PAGAMENTO,
            "prestacao_conferida",
            usuario,
            comentario,
            agora,
        )
        texto = (
            f"A prestação de contas foi conferida. Você gastou {moeda(-diferenca)} a mais; "
            "como você é gestor, a diferença segue direto para pagamento."
        )
    else:
        _mudar(
            db,
            sol,
            DIFERENCA_AGUARDANDO_GESTOR,
            "prestacao_conferida",
            usuario,
            comentario,
            agora,
        )
        texto = (
            f"A prestação de contas foi conferida. Você gastou {moeda(-diferenca)} a mais; "
            "a diferença foi para a aprovação do seu gestor."
        )
    notificacoes.enfileirar(
        db, settings, sol, interessados(sol), "Prestação de contas conferida", texto
    )
    # Resumo para a Thais e o gestor (só informativo, exceto quando há diferença a aprovar).
    resumo = _resumo_prestacao(sol)
    if sol.gestor_email:
        acao_gestor = (
            "\nA diferença precisa da sua aprovação."
            if sol.status == DIFERENCA_AGUARDANDO_GESTOR
            else ""
        )
        notificacoes.enfileirar(
            db,
            settings,
            sol,
            [sol.gestor_email],
            "Resumo da prestação de contas",
            resumo + acao_gestor,
        )
    notificacoes.enfileirar(
        db,
        settings,
        sol,
        notificacoes.emails_financeiro(db),
        "Resumo da prestação de contas",
        resumo,
    )
    db.commit()
    return sol


def _decidir_diferenca(
    db: Session,
    settings: Settings,
    sol: Solicitacao,
    usuario: Usuario,
    aprovar: bool,
    comentario: str | None,
) -> Solicitacao:
    agora = agora_utc()
    if not aprovar:
        return _recusar(db, settings, sol, usuario, comentario, agora)
    sol.diferenca_aprovada_por, sol.diferenca_aprovada_em = usuario.nome, agora
    _mudar(
        db, sol, DIFERENCA_AGUARDANDO_PAGAMENTO, "diferenca_aprovada", usuario, comentario, agora
    )
    falta = -(saldo(sol) or Decimal("0.00"))
    notificacoes.enfileirar(
        db,
        settings,
        sol,
        interessados(sol),
        "Diferença aprovada",
        f"{usuario.nome} aprovou a diferença de {moeda(falta)}. Agora falta o pagamento.",
    )
    notificacoes.enfileirar(
        db,
        settings,
        sol,
        notificacoes.emails_financeiro(db),
        "Diferença aprovada — pagar",
        f"{usuario.nome} aprovou a diferença de {moeda(falta)} do adiantamento.",
    )
    db.commit()
    return sol


def _pagar_diferenca(
    db: Session, settings: Settings, sol: Solicitacao, usuario: Usuario, data_pagamento: date
) -> Solicitacao:
    agora = agora_utc()
    sol.data_pagamento_diferenca = data_pagamento
    _encerrar(
        db, sol, "diferenca_paga", usuario, f"Diferença paga em {data_pagamento:%d/%m/%Y}", agora
    )
    falta = -(saldo(sol) or Decimal("0.00"))
    notificacoes.enfileirar(
        db,
        settings,
        sol,
        interessados(sol),
        "Diferença paga",
        f"A diferença de {moeda(falta)} foi paga em {data_pagamento:%d/%m/%Y}. "
        "O adiantamento está encerrado.",
    )
    db.commit()
    return sol


def _encerrar(
    db: Session,
    sol: Solicitacao,
    acao: str,
    usuario: Usuario,
    comentario: str | None,
    agora: datetime,
) -> None:
    sol.encerrado_em = agora
    _mudar(db, sol, ENCERRADO, acao, usuario, comentario, agora)


def _resumo_prestacao(sol: Solicitacao) -> str:
    diferenca = saldo(sol) or Decimal("0.00")
    if diferenca > 0:
        resultado = f"Sobrou {moeda(diferenca)} (o colaborador vai devolver)."
    elif diferenca < 0:
        resultado = f"Gastou {moeda(-diferenca)} a mais (diferença a reembolsar)."
    else:
        resultado = "Bateu certinho (encerrada)."
    notas = len([d for d in sol.despesas if d.categoria != COMPROVANTE_DEVOLUCAO])
    return (
        f"Prestação de contas do adiantamento de {sol.solicitante_nome} "
        f"({sol.destino}).\n"
        f"Adiantado: {moeda(sol.valor_total)} ({_descrever_diarias(sol)}).\n"
        f"Gasto comprovado: {moeda(sol.valor_gasto or 0)} em {notas} nota(s).\n"
        f"{resultado}"
    )


def _avisar_pedido_adiantamento(
    db: Session, settings: Settings, sol: Solicitacao, quem: str
) -> None:
    if sol.status == AGUARDANDO_GESTOR:
        notificacoes.enfileirar(
            db,
            settings,
            sol,
            [sol.gestor_email or ""],
            "Adiantamento aguardando sua aprovação",
            f"{quem} um adiantamento de {_descrever_diarias(sol)} para {sol.destino}.",
        )
    else:
        notificacoes.enfileirar(
            db,
            settings,
            sol,
            notificacoes.emails_financeiro(db),
            "Adiantamento para pagar",
            f"{quem} um adiantamento de {_descrever_diarias(sol)} para {sol.destino}. "
            "Como o solicitante é gestor, não passa por aprovação.",
        )


def _descrever_diarias(sol: Solicitacao) -> str:
    if sol.valor_complementar is not None:
        return f"{sol.diarias} diária(s) + diária complementar de {moeda(sol.valor_complementar)}"
    return f"{sol.diarias} diária(s)"


def _validar_adiantamento(dados: DadosAdiantamento) -> int:
    if not dados.destino.strip():
        raise RegraNegocio("Informe o destino da viagem.")
    if len(dados.destino) > 200:
        raise RegraNegocio("Destino muito longo (máximo 200 caracteres).")
    if dados.fim < dados.inicio:
        raise RegraNegocio("O fim da viagem não pode ser antes do início.")
    if not dados.descricao.strip():
        raise RegraNegocio("Explique o motivo da viagem.")
    if len(dados.descricao) > 500:
        raise RegraNegocio("Justificativa muito longa (máximo 500 caracteres).")
    if dados.complementar is not None and dados.complementar <= 0:
        raise RegraNegocio("Informe o valor da diária complementar.")
    diarias = calcular_diarias(dados.inicio, dados.fim)
    if diarias > MAX_DIARIAS:
        raise RegraNegocio(
            f"Período longo demais ({diarias} dias). Confira as datas "
            f"(máximo {MAX_DIARIAS} diárias)."
        )
    return diarias


def _valor_adiantamento(dados: DadosAdiantamento, diarias: int) -> Decimal:
    """Diárias normais + diária complementar (se houver), que SOMA (Thais, 13/10)."""
    return VALOR_DIARIA * diarias + (dados.complementar or Decimal("0.00"))


def _alerta_total(valor: Decimal) -> str | None:
    if valor > LIMITE_SOLICITACAO:
        return f"Total acima do limite por solicitação ({moeda(LIMITE_SOLICITACAO)})."
    return None


# ---------------------------------------------------------------------------
# Decisões
# ---------------------------------------------------------------------------
def conferir(
    db: Session,
    settings: Settings,
    usuario: Usuario,
    sol_id: int,
    aprovar: bool,
    comentario: str | None,
) -> Solicitacao:
    sol = obter(db, usuario, sol_id)
    _exigir(usuario.tem(FINANCEIRO), "Só o financeiro confere.")
    _exigir(not eh_dono(sol, usuario), OUTRO_FINANCEIRO)
    if sol.status == PRESTACAO_EM_CONFERENCIA:
        return _conferir_prestacao(db, settings, sol, usuario, aprovar, comentario)
    _exigir_status(sol, EM_CONFERENCIA)
    agora = agora_utc()
    if not aprovar:
        return _devolver(db, settings, sol, usuario, comentario, agora)

    sol.conferido_por, sol.conferido_em = usuario.nome, agora
    if sol.pula_gestor:
        _mudar(db, sol, AGUARDANDO_PAGAMENTO, "conferido", usuario, comentario, agora)
        texto = "A nota foi conferida. Como você é gestor, segue direto para pagamento."
    else:
        _mudar(db, sol, AGUARDANDO_GESTOR, "conferido", usuario, comentario, agora)
        notificacoes.enfileirar(
            db,
            settings,
            sol,
            [sol.gestor_email or ""],
            "Reembolso aguardando sua aprovação",
            f"{sol.solicitante_nome} pediu um reembolso, já conferido pelo financeiro.",
        )
        texto = "A nota foi conferida pelo financeiro e seguiu para o seu gestor."
    notificacoes.enfileirar(db, settings, sol, interessados(sol), "Solicitação conferida", texto)
    db.commit()
    return sol


def decidir_gestor(
    db: Session,
    settings: Settings,
    usuario: Usuario,
    sol_id: int,
    aprovar: bool,
    comentario: str | None,
) -> Solicitacao:
    sol = obter(db, usuario, sol_id)
    _exigir(
        usuario.tem(GESTOR) and sol.gestor_email == usuario.email,
        "Só o gestor escolhido pode aprovar.",
    )
    if sol.status == DIFERENCA_AGUARDANDO_GESTOR:
        return _decidir_diferenca(db, settings, sol, usuario, aprovar, comentario)
    _exigir_status(sol, AGUARDANDO_GESTOR)
    agora = agora_utc()
    if not aprovar:
        return _recusar(db, settings, sol, usuario, comentario, agora)

    sol.aprovado_por, sol.aprovado_em = usuario.nome, agora
    _mudar(db, sol, AGUARDANDO_PAGAMENTO, "aprovado", usuario, comentario, agora)
    notificacoes.enfileirar(
        db,
        settings,
        sol,
        interessados(sol),
        "Solicitação aprovada",
        f"{usuario.nome} aprovou. Agora falta o pagamento.",
    )
    notificacoes.enfileirar(
        db,
        settings,
        sol,
        notificacoes.emails_financeiro(db),
        "Reembolso aprovado — pagar",
        f"{usuario.nome} aprovou o reembolso.",
    )
    db.commit()
    return sol


def pagar(
    db: Session, settings: Settings, usuario: Usuario, sol_id: int, data_pagamento: date
) -> Solicitacao:
    sol = obter(db, usuario, sol_id)
    _exigir(usuario.tem(FINANCEIRO), "Só o financeiro registra pagamento.")
    if sol.status == DIFERENCA_AGUARDANDO_PAGAMENTO:
        return _pagar_diferenca(db, settings, sol, usuario, data_pagamento)
    _exigir_status(sol, AGUARDANDO_PAGAMENTO)
    agora = agora_utc()
    sol.pago_por, sol.pago_em, sol.data_pagamento = usuario.nome, agora, data_pagamento
    comentario = f"Pagamento em {data_pagamento:%d/%m/%Y}"
    if sol.tipo == TIPO_ADIANTAMENTO:
        _mudar(db, sol, AGUARDANDO_PRESTACAO, "pago", usuario, comentario, agora)
        notificacoes.enfileirar(
            db,
            settings,
            sol,
            interessados(sol),
            "Adiantamento pago",
            f"O adiantamento foi pago em {data_pagamento:%d/%m/%Y}. Depois da viagem, "
            "faça a prestação de contas no sistema, com as notas.",
        )
    else:
        _mudar(db, sol, PAGO, "pago", usuario, comentario, agora)
        notificacoes.enfileirar(
            db,
            settings,
            sol,
            interessados(sol),
            "Reembolso pago",
            f"O reembolso foi pago em {data_pagamento:%d/%m/%Y}.",
        )
    db.commit()
    return sol


def processar_expiracoes(db: Session, settings: Settings, agora: datetime | None = None) -> dict:
    """Devolvidas paradas: lembra 2 dias antes e cancela no prazo. Adiantamentos
    sem prestação de contas: lembra antes do prazo e avisa quando vence.
    Idempotente."""
    agora = agora or agora_utc()
    lembretes = cancelamentos = 0
    devolvidas = db.scalars(select(Solicitacao).where(Solicitacao.status == DEVOLVIDO)).all()
    for sol in devolvidas:
        parada = agora - sol.ultima_movimentacao_em
        if parada >= timedelta(days=DIAS_EXPIRACAO_DEVOLVIDO):
            motivo = f"Devolvida e sem correção por {DIAS_EXPIRACAO_DEVOLVIDO} dias."
            sol.cancelado_em, sol.motivo_cancelamento = agora, motivo
            _mudar(db, sol, CANCELADO, "cancelado", SISTEMA, motivo, agora)
            notificacoes.enfileirar(
                db,
                settings,
                sol,
                interessados(sol),
                "Solicitação cancelada",
                f"{motivo} Se ainda precisar do reembolso, abra uma nova solicitação.",
            )
            cancelamentos += 1
        elif (
            parada >= timedelta(days=DIAS_LEMBRETE_DEVOLVIDO) and sol.lembrete_expiracao_em is None
        ):
            sol.lembrete_expiracao_em = agora
            faltam = DIAS_EXPIRACAO_DEVOLVIDO - DIAS_LEMBRETE_DEVOLVIDO
            notificacoes.enfileirar(
                db,
                settings,
                sol,
                interessados(sol),
                "Lembrete: corrija sua solicitação",
                f"Sua solicitação está devolvida. Se não for corrigida em {faltam} dias, "
                "será cancelada.",
            )
            lembretes += 1
    lembretes_prestacao, prestacoes_vencidas = _verificar_prazo_prestacao(db, settings, agora)
    db.commit()
    if lembretes or cancelamentos or lembretes_prestacao or prestacoes_vencidas:
        log.info(
            "Expiração: %s lembrete(s), %s cancelamento(s); prestação: %s lembrete(s), "
            "%s vencida(s).",
            lembretes,
            cancelamentos,
            lembretes_prestacao,
            prestacoes_vencidas,
        )
    return {
        "lembretes": lembretes,
        "cancelamentos": cancelamentos,
        "lembretes_prestacao": lembretes_prestacao,
        "prestacoes_vencidas": prestacoes_vencidas,
    }


def _verificar_prazo_prestacao(db: Session, settings: Settings, agora: datetime) -> tuple[int, int]:
    hoje = agora.date()
    lembretes = vencidas = 0
    pendentes = db.scalars(
        select(Solicitacao).where(Solicitacao.status == AGUARDANDO_PRESTACAO)
    ).all()
    for sol in pendentes:
        prazo = prazo_prestacao(sol)
        if prazo is None:
            continue
        if hoje > prazo and sol.aviso_prestacao_vencida_em is None:
            sol.aviso_prestacao_vencida_em = agora
            notificacoes.enfileirar(
                db,
                settings,
                sol,
                [sol.solicitante_email, *notificacoes.emails_financeiro(db)],
                "Prestação de contas atrasada",
                f"O prazo da prestação de contas do adiantamento ({sol.destino}) venceu em "
                f"{prazo:%d/%m/%Y}. Envie as notas o quanto antes.",
            )
            vencidas += 1
        elif (
            hoje >= prazo - timedelta(days=DIAS_LEMBRETE_PRESTACAO)
            and hoje <= prazo
            and sol.lembrete_prestacao_em is None
        ):
            sol.lembrete_prestacao_em = agora
            notificacoes.enfileirar(
                db,
                settings,
                sol,
                interessados(sol),
                "Lembrete: prestação de contas",
                f"A prestação de contas do adiantamento ({sol.destino}) vence em "
                f"{prazo:%d/%m/%Y}. Envie as notas pelo sistema.",
            )
            lembretes += 1
    return lembretes, vencidas


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------
def _devolver(
    db: Session,
    settings: Settings,
    sol: Solicitacao,
    usuario: Usuario,
    comentario: str | None,
    agora: datetime,
    para: str = DEVOLVIDO,
) -> Solicitacao:
    motivo = (comentario or "").strip()
    if not motivo:
        raise RegraNegocio("Explique o que precisa ser corrigido.")
    sol.devolvido_por, sol.devolvido_em, sol.motivo_devolucao = usuario.nome, agora, motivo
    sol.lembrete_expiracao_em = None
    _mudar(db, sol, para, "devolvido", usuario, motivo, agora)
    if para == DEVOLVIDO:
        texto = (
            f"{usuario.nome} devolveu: {motivo}\nCorrija em até {DIAS_EXPIRACAO_DEVOLVIDO} dias."
        )
    else:
        # Prestação de contas: o dinheiro já foi pago, então não cancela sozinha.
        texto = f"{usuario.nome} devolveu a prestação de contas: {motivo}"
    notificacoes.enfileirar(
        db,
        settings,
        sol,
        interessados(sol),
        "Solicitação devolvida para correção",
        texto,
    )
    db.commit()
    return sol


def _recusar(
    db: Session,
    settings: Settings,
    sol: Solicitacao,
    usuario: Usuario,
    comentario: str | None,
    agora: datetime,
) -> Solicitacao:
    """Recusa do gestor: finaliza o pedido (Thais, 15/10). Para tentar de novo,
    o colaborador abre um pedido novo."""
    motivo = (comentario or "").strip()
    if not motivo:
        raise RegraNegocio("Explique o motivo da recusa.")
    sol.recusado_por, sol.recusado_em, sol.motivo_recusa = usuario.nome, agora, motivo
    _mudar(db, sol, RECUSADO, "recusado", usuario, motivo, agora)
    notificacoes.enfileirar(
        db,
        settings,
        sol,
        interessados(sol),
        "Solicitação recusada pelo gestor",
        f"{usuario.nome} recusou: {motivo}\nO pedido foi finalizado. "
        "Se quiser tentar de novo, abra um pedido novo.",
    )
    db.commit()
    return sol


def _mudar(
    db: Session,
    sol: Solicitacao,
    novo: str,
    acao: str,
    usuario: Usuario,
    comentario: str | None,
    agora: datetime,
) -> None:
    anterior = sol.status
    sol.status = novo
    sol.ultima_movimentacao_em = agora
    _registrar(db, sol, acao, anterior, novo, usuario, comentario, agora)


def _registrar(
    db: Session,
    sol: Solicitacao,
    acao: str,
    de: str | None,
    para: str,
    usuario: Usuario,
    comentario: str | None,
    agora: datetime,
) -> None:
    sol.historico.append(
        Historico(
            acao=acao,
            status_de=de,
            status_para=para,
            usuario_email=usuario.email,
            usuario_nome=usuario.nome,
            comentario=(comentario or "").strip() or None,
            criado_em=agora,
        )
    )


def _pessoa_do_pedido(
    db: Session, settings: Settings, usuario: Usuario, beneficiario: Beneficiario | None
) -> _Pessoa:
    """Quem recebe o reembolso: o próprio usuário ou o beneficiário informado."""
    if beneficiario is None or beneficiario.email.strip().lower() == usuario.email:
        perfil = db.scalar(select(CadastroUsuario).where(CadastroUsuario.email == usuario.email))
        if perfil is None or not perfil.perfil_completo:
            raise RegraNegocio("Complete seu perfil (matrícula) antes de pedir.")
        return _Pessoa(
            email=usuario.email,
            nome=usuario.nome,
            matricula=perfil.matricula or "",
            eh_gestor=usuario.tem(GESTOR),
        )

    email = beneficiario.email.strip().lower()
    if not EMAIL_VALIDO.match(email) or len(email) > 254:
        raise RegraNegocio("E-mail da pessoa do pedido inválido.")
    cadastro = db.scalar(select(CadastroUsuario).where(CadastroUsuario.email == email))
    eh_gestor = (cadastro is not None and GESTOR in cadastro.lista_papeis) or (
        gestores.buscar(db, settings, email) is not None
    )
    if cadastro is not None and cadastro.perfil_completo:
        # Já usa o sistema: vale o perfil dela (o que foi digitado é ignorado).
        nome, matricula = cadastro.nome, cadastro.matricula or ""
    else:
        nome = beneficiario.nome.strip() or (cadastro.nome if cadastro else "")
        matricula = beneficiario.matricula.strip()
        if not nome or len(nome) > 200:
            raise RegraNegocio("Informe o nome da pessoa do pedido.")
        if not matricula or len(matricula) > 30:
            raise RegraNegocio("Informe a matrícula da pessoa do pedido.")
    return _Pessoa(
        email=email,
        nome=nome,
        matricula=matricula,
        eh_gestor=eh_gestor,
        criado_por_email=usuario.email,
        criado_por_nome=usuario.nome,
    )


def _autor(usuario: Usuario, sol: Solicitacao) -> str:
    """ "Ana" ou "Ana (em nome de Bruno)", para os avisos."""
    if sol.criado_por_email and sol.criado_por_email != sol.solicitante_email:
        return f"{usuario.nome} (em nome de {sol.solicitante_nome})"
    return usuario.nome


def _validar_gestor(
    db: Session,
    settings: Settings,
    pessoa_email: str,
    criado_por_email: str | None,
    email: str | None,
) -> gestores.Gestor:
    if not email:
        raise RegraNegocio("Escolha o gestor que vai aprovar.")
    escolhido = email.strip().lower()
    if escolhido == pessoa_email:
        if criado_por_email and criado_por_email != pessoa_email:
            raise RegraNegocio("A pessoa do pedido não pode ser a própria aprovadora.")
        raise RegraNegocio("Você não pode ser o seu próprio aprovador.")
    if criado_por_email and escolhido == criado_por_email:
        raise RegraNegocio("Quem criou o pedido não pode ser o aprovador.")
    gestor = gestores.buscar(db, settings, email)
    if gestor is None:
        raise RegraNegocio("Gestor não encontrado na lista de gestores.")
    return gestor


def _empresa(db: Session, empresa_id: int) -> Empresa:
    empresa = db.get(Empresa, empresa_id)
    if empresa is None or not empresa.ativo:
        raise RegraNegocio("Empresa de débito inválida.")
    return empresa


def _centro_custo(db: Session, centro_custo_id: int | None) -> CentroCusto:
    centro = db.get(CentroCusto, centro_custo_id) if centro_custo_id else None
    if centro is None or not centro.ativo:
        raise RegraNegocio("Escolha o centro de custo.")
    return centro


def _lembrar_centro_custo(db: Session, usuario: Usuario, centro: CentroCusto) -> None:
    """Guarda o último centro de custo usado por quem preencheu, para sugerir
    no próximo pedido (Thais, 15/10: vem preenchido, mas dá para trocar)."""
    cadastro = db.scalar(select(CadastroUsuario).where(CadastroUsuario.email == usuario.email))
    if cadastro is not None:
        cadastro.centro_custo_id = centro.id


def _exigir(condicao: bool, mensagem: str) -> None:
    if not condicao:
        raise SemPermissao(mensagem)


def _exigir_status(sol: Solicitacao, esperado: str) -> None:
    if sol.status != esperado:
        raise RegraNegocio(
            f'Esta solicitação está "{ROTULO_STATUS.get(sol.status, sol.status)}"; '
            "a ação não se aplica mais."
        )
