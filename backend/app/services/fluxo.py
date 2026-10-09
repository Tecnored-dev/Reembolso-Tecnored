"""Fluxo das solicitações de reembolso: ALIMENTAÇÃO e VIAGEM.

O reembolso de viagem (o colaborador pagou e pede depois, com as notas) segue
o MESMO fluxo da alimentação; a diferença é aceitar várias notas, cada uma com
categoria. O adiantamento de diárias tem fluxo próprio e ainda não está aqui.

Regras (Thais, 06/10/2026 — docs do projeto `fluxos-aprovacao.md`):

    colaborador envia ─▶ EM_CONFERENCIA (financeiro confere dados e nota)
        │ devolve ─▶ DEVOLVIDO ─(colaborador corrige e reenvia)─▶ EM_CONFERENCIA
        ▼ ok
    AGUARDANDO_GESTOR (o gestor escolhido aprova)      ← pulado se o solicitante é gestor
        │ devolve ─▶ DEVOLVIDO  (o reenvio volta para a conferência, nunca direto ao gestor)
        ▼ aprova
    AGUARDANDO_PAGAMENTO ─(financeiro paga e informa a data)─▶ PAGO

- Depois de enviar, o colaborador não edita nem cancela; só corrige quando devolvido.
- Devolvida e parada: lembrete no 5º dia, cancelada no 7º.
- Alertas (não bloqueiam): refeição acima do limite diário (somando as notas
  do mesmo dia) e total acima do limite por solicitação.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.papeis import ADMIN, FINANCEIRO, GESTOR
from app.auth.sessoes import Usuario, agora_utc
from app.config import (
    CATEGORIAS_VIAGEM,
    DIAS_EXPIRACAO_DEVOLVIDO,
    DIAS_LEMBRETE_DEVOLVIDO,
    LIMITE_REFEICAO_DIA,
    LIMITE_SOLICITACAO,
    MAX_DESPESAS_VIAGEM,
    Settings,
)
from app.models.cadastros import Empresa
from app.models.cadastros import Usuario as CadastroUsuario
from app.models.solicitacao import Despesa, Historico, Solicitacao
from app.services import arquivos, gestores, notificacoes
from app.services.erros import NaoEncontrado, RegraNegocio, SemPermissao
from app.services.formatos import moeda
from app.storage import Armazenamento

log = logging.getLogger(__name__)

TIPO_ALIMENTACAO = "alimentacao"
TIPO_VIAGEM = "viagem"
ROTULO_TIPO = {TIPO_ALIMENTACAO: "Alimentação", TIPO_VIAGEM: "Viagem"}

EM_CONFERENCIA = "em_conferencia"
AGUARDANDO_GESTOR = "aguardando_gestor"
AGUARDANDO_PAGAMENTO = "aguardando_pagamento"
PAGO = "pago"
DEVOLVIDO = "devolvido"
CANCELADO = "cancelado"

ROTULO_STATUS = {
    EM_CONFERENCIA: "Em conferência (financeiro)",
    AGUARDANDO_GESTOR: "Aguardando aprovação do gestor",
    AGUARDANDO_PAGAMENTO: "Aprovada — aguardando pagamento",
    PAGO: "Paga",
    DEVOLVIDO: "Devolvida para correção",
    CANCELADO: "Cancelada",
}

SISTEMA = Usuario(email="sistema", nome="Sistema", papeis=(), via="sistema")


@dataclass(frozen=True)
class DadosAlimentacao:
    data_despesa: date
    valor: Decimal
    descricao: str
    empresa_id: int
    gestor_email: str | None


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
class DadosViagem:
    destino: str
    inicio: date
    fim: date
    descricao: str  # justificativa
    empresa_id: int
    gestor_email: str | None
    itens: tuple[ItemViagem, ...]


# ---------------------------------------------------------------------------
# Leitura e visibilidade
# ---------------------------------------------------------------------------
def pode_ver(sol: Solicitacao, usuario: Usuario) -> bool:
    return (
        sol.solicitante_email == usuario.email
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
        consulta = consulta.where(Solicitacao.solicitante_email == usuario.email)
    elif escopo == "conferencia":
        _exigir(usuario.tem(FINANCEIRO), "Só o financeiro confere.")
        consulta = consulta.where(Solicitacao.status == EM_CONFERENCIA)
    elif escopo == "aprovacao":
        _exigir(usuario.tem(GESTOR), "Só gestores aprovam.")
        consulta = consulta.where(
            Solicitacao.status == AGUARDANDO_GESTOR,
            Solicitacao.gestor_email == usuario.email,
        )
    elif escopo == "pagamento":
        _exigir(usuario.tem(FINANCEIRO), "Só o financeiro paga.")
        consulta = consulta.where(Solicitacao.status == AGUARDANDO_PAGAMENTO)
    elif escopo == "todas":
        if not (usuario.tem(FINANCEIRO) or usuario.tem(ADMIN)):
            # Gestor vê as que passaram por ele; colaborador, as próprias.
            consulta = consulta.where(
                or_(
                    Solicitacao.solicitante_email == usuario.email,
                    Solicitacao.gestor_email == usuario.email,
                )
            )
    else:
        raise RegraNegocio(f"Escopo inválido: {escopo}")
    return list(db.scalars(consulta).all())


def acoes_disponiveis(sol: Solicitacao, usuario: Usuario) -> list[str]:
    acoes = []
    if sol.status == EM_CONFERENCIA and usuario.tem(FINANCEIRO):
        acoes += ["conferir", "devolver"]
    if (
        sol.status == AGUARDANDO_GESTOR
        and usuario.tem(GESTOR)
        and sol.gestor_email == usuario.email
    ):
        acoes += ["aprovar", "devolver"]
    if sol.status == AGUARDANDO_PAGAMENTO and usuario.tem(FINANCEIRO):
        acoes.append("pagar")
    if sol.status == DEVOLVIDO and sol.solicitante_email == usuario.email:
        acoes.append("reenviar")
    return acoes


# ---------------------------------------------------------------------------
# Criação e reenvio
# ---------------------------------------------------------------------------
def criar_alimentacao(
    db: Session,
    settings: Settings,
    armazenamento: Armazenamento,
    usuario: Usuario,
    dados: DadosAlimentacao,
    arquivo: arquivos.ArquivoValidado,
) -> Solicitacao:
    perfil = db.scalar(select(CadastroUsuario).where(CadastroUsuario.email == usuario.email))
    if perfil is None or not perfil.perfil_completo or perfil.centro_custo is None:
        raise RegraNegocio("Complete seu perfil (matrícula e centro de custo) antes de pedir.")

    agora = agora_utc()
    pula_gestor = usuario.tem(GESTOR)
    gestor = None if pula_gestor else _validar_gestor(db, settings, usuario, dados.gestor_email)
    _validar_basico(dados)
    empresa = _empresa(db, dados.empresa_id)

    sol = Solicitacao(
        tipo=TIPO_ALIMENTACAO,
        status=EM_CONFERENCIA,
        solicitante_email=usuario.email,
        solicitante_nome=usuario.nome,
        matricula=perfil.matricula,
        centro_custo=perfil.centro_custo.rotulo,
        empresa=empresa.nome,
        gestor_email=gestor.email if gestor else None,
        gestor_nome=gestor.nome if gestor else None,
        pula_gestor=pula_gestor,
        descricao=dados.descricao.strip(),
        valor_total=dados.valor,
        alerta_limite=_alerta(dados.valor),
        enviado_em=agora,
        ultima_movimentacao_em=agora,
    )
    db.add(sol)
    db.flush()  # gera o id
    sol.codigo = f"REE-{sol.id:06d}"

    chave = arquivos.salvar(armazenamento, arquivo, sol.codigo, agora)
    try:
        sol.despesas.append(_despesa(dados, arquivo, chave, agora))
        _registrar(db, sol, "enviado", None, EM_CONFERENCIA, usuario, None, agora)
        notificacoes.enfileirar(
            db,
            settings,
            sol,
            notificacoes.emails_financeiro(db),
            "Nova solicitação para conferir",
            f"{usuario.nome} enviou um reembolso de alimentação para conferência.",
        )
        db.commit()
    except Exception:
        db.rollback()
        armazenamento.remover(chave)
        raise
    return sol


def reenviar(
    db: Session,
    settings: Settings,
    armazenamento: Armazenamento,
    usuario: Usuario,
    sol_id: int,
    dados: DadosAlimentacao,
    arquivo: arquivos.ArquivoValidado | None,
) -> Solicitacao:
    sol = obter(db, usuario, sol_id)
    _exigir(sol.solicitante_email == usuario.email, "Só quem pediu pode corrigir.")
    _exigir_status(sol, DEVOLVIDO)
    if sol.tipo != TIPO_ALIMENTACAO:
        raise RegraNegocio("Esta solicitação não é de alimentação.")
    _validar_basico(dados)
    if not sol.pula_gestor:
        gestor = _validar_gestor(db, settings, usuario, dados.gestor_email)
        sol.gestor_email, sol.gestor_nome = gestor.email, gestor.nome
    sol.empresa = _empresa(db, dados.empresa_id).nome
    sol.descricao = dados.descricao.strip()
    sol.valor_total = dados.valor
    sol.alerta_limite = _alerta(dados.valor)

    agora = agora_utc()
    despesa = sol.despesas[0]
    despesa.data_despesa, despesa.valor = dados.data_despesa, dados.valor
    chave_antiga = None
    if arquivo is not None:
        chave_antiga = despesa.arquivo_chave
        despesa.arquivo_chave = arquivos.salvar(armazenamento, arquivo, sol.codigo or "", agora)
        despesa.arquivo_nome, despesa.arquivo_tipo = arquivo.nome, arquivo.tipo
        despesa.arquivo_tamanho = len(arquivo.conteudo)

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
    try:
        db.commit()
    except Exception:
        db.rollback()
        if arquivo is not None:
            armazenamento.remover(despesa.arquivo_chave)
        raise
    if chave_antiga:
        armazenamento.remover(chave_antiga)
    return sol


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
    perfil = db.scalar(select(CadastroUsuario).where(CadastroUsuario.email == usuario.email))
    if perfil is None or not perfil.perfil_completo or perfil.centro_custo is None:
        raise RegraNegocio("Complete seu perfil (matrícula e centro de custo) antes de pedir.")
    # Na criação nenhuma nota existe ainda: qualquer `id` é recusado.
    _validar_viagem(dados, arquivos_enviados, existentes=set())

    agora = agora_utc()
    pula_gestor = usuario.tem(GESTOR)
    gestor = None if pula_gestor else _validar_gestor(db, settings, usuario, dados.gestor_email)
    empresa = _empresa(db, dados.empresa_id)

    sol = Solicitacao(
        tipo=TIPO_VIAGEM,
        status=EM_CONFERENCIA,
        solicitante_email=usuario.email,
        solicitante_nome=usuario.nome,
        matricula=perfil.matricula,
        centro_custo=perfil.centro_custo.rotulo,
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
        notificacoes.enfileirar(
            db,
            settings,
            sol,
            notificacoes.emails_financeiro(db),
            "Nova solicitação para conferir",
            f"{usuario.nome} enviou um reembolso de viagem ({dados.destino.strip()}) "
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
    _exigir(sol.solicitante_email == usuario.email, "Só quem pediu pode corrigir.")
    _exigir_status(sol, DEVOLVIDO)
    if sol.tipo != TIPO_VIAGEM:
        raise RegraNegocio("Esta solicitação não é de viagem.")
    atuais = {d.id: d for d in sol.despesas}
    _validar_viagem(dados, arquivos_enviados, existentes=set(atuais))
    if not sol.pula_gestor:
        gestor = _validar_gestor(db, settings, usuario, dados.gestor_email)
        sol.gestor_email, sol.gestor_nome = gestor.email, gestor.nome
    sol.empresa = _empresa(db, dados.empresa_id).nome
    sol.descricao = dados.descricao.strip()
    sol.destino = dados.destino.strip()
    sol.viagem_inicio, sol.viagem_fim = dados.inicio, dados.fim
    sol.valor_total = _total(dados.itens)
    sol.alerta_limite = _alerta_viagem(dados.itens)

    agora = agora_utc()
    novas_chaves: list[str] = []
    chaves_antigas: list[str] = []
    try:
        mantidas = {item.id for item in dados.itens if item.id is not None}
        for despesa_id, despesa in atuais.items():
            if despesa_id not in mantidas:
                chaves_antigas.append(despesa.arquivo_chave)
                sol.despesas.remove(despesa)
        for item in dados.itens:
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


def _validar_viagem(
    dados: DadosViagem, arquivos_enviados: list[arquivos.ArquivoValidado], existentes: set[int]
) -> None:
    hoje = date.today()
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
    if not dados.itens:
        raise RegraNegocio("Inclua pelo menos uma nota.")
    if len(dados.itens) > MAX_DESPESAS_VIAGEM:
        raise RegraNegocio(f"Máximo de {MAX_DESPESAS_VIAGEM} notas por solicitação.")

    usados: set[int] = set()
    ids: set[int] = set()
    for n, item in enumerate(dados.itens, start=1):
        if item.categoria not in CATEGORIAS_VIAGEM:
            raise RegraNegocio(f"Nota {n}: categoria inválida.")
        if item.data_despesa > hoje:
            raise RegraNegocio(f"Nota {n}: a data não pode ser no futuro.")
        if len(item.descricao) > 200:
            raise RegraNegocio(f"Nota {n}: descrição muito longa (máximo 200 caracteres).")
        if item.categoria == "outros" and not item.descricao.strip():
            raise RegraNegocio(f"Nota {n}: descreva a despesa da categoria Outros.")
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
    notificacoes.enfileirar(
        db, settings, sol, [sol.solicitante_email], "Solicitação conferida", texto
    )
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
    _exigir_status(sol, AGUARDANDO_GESTOR)
    agora = agora_utc()
    if not aprovar:
        return _devolver(db, settings, sol, usuario, comentario, agora)

    sol.aprovado_por, sol.aprovado_em = usuario.nome, agora
    _mudar(db, sol, AGUARDANDO_PAGAMENTO, "aprovado", usuario, comentario, agora)
    notificacoes.enfileirar(
        db,
        settings,
        sol,
        [sol.solicitante_email],
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
    _exigir_status(sol, AGUARDANDO_PAGAMENTO)
    agora = agora_utc()
    sol.pago_por, sol.pago_em, sol.data_pagamento = usuario.nome, agora, data_pagamento
    _mudar(db, sol, PAGO, "pago", usuario, f"Pagamento em {data_pagamento:%d/%m/%Y}", agora)
    notificacoes.enfileirar(
        db,
        settings,
        sol,
        [sol.solicitante_email],
        "Reembolso pago",
        f"O reembolso foi pago em {data_pagamento:%d/%m/%Y}.",
    )
    db.commit()
    return sol


def processar_expiracoes(db: Session, settings: Settings, agora: datetime | None = None) -> dict:
    """Lembra no 5º dia e cancela no 7º as devolvidas paradas. Idempotente."""
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
                [sol.solicitante_email],
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
                [sol.solicitante_email],
                "Lembrete: corrija sua solicitação",
                f"Sua solicitação está devolvida. Se não for corrigida em {faltam} dias, "
                "será cancelada.",
            )
            lembretes += 1
    db.commit()
    if lembretes or cancelamentos:
        log.info("Expiração: %s lembrete(s), %s cancelamento(s).", lembretes, cancelamentos)
    return {"lembretes": lembretes, "cancelamentos": cancelamentos}


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
) -> Solicitacao:
    motivo = (comentario or "").strip()
    if not motivo:
        raise RegraNegocio("Explique o que precisa ser corrigido.")
    sol.devolvido_por, sol.devolvido_em, sol.motivo_devolucao = usuario.nome, agora, motivo
    sol.lembrete_expiracao_em = None
    _mudar(db, sol, DEVOLVIDO, "devolvido", usuario, motivo, agora)
    notificacoes.enfileirar(
        db,
        settings,
        sol,
        [sol.solicitante_email],
        "Solicitação devolvida para correção",
        f"{usuario.nome} devolveu: {motivo}\nCorrija em até {DIAS_EXPIRACAO_DEVOLVIDO} dias.",
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


def _validar_basico(dados: DadosAlimentacao) -> None:
    if dados.data_despesa > date.today():
        raise RegraNegocio("A data da despesa não pode ser no futuro.")
    if not dados.descricao.strip():
        raise RegraNegocio("Descreva a despesa.")
    if len(dados.descricao) > 500:
        raise RegraNegocio("Descrição muito longa (máximo 500 caracteres).")


def _validar_gestor(
    db: Session, settings: Settings, usuario: Usuario, email: str | None
) -> gestores.Gestor:
    if not email:
        raise RegraNegocio("Escolha o gestor que vai aprovar.")
    if email.strip().lower() == usuario.email:
        raise RegraNegocio("Você não pode ser o seu próprio aprovador.")
    gestor = gestores.buscar(db, settings, email)
    if gestor is None:
        raise RegraNegocio("Gestor não encontrado na lista de gestores.")
    return gestor


def _empresa(db: Session, empresa_id: int) -> Empresa:
    empresa = db.get(Empresa, empresa_id)
    if empresa is None or not empresa.ativo:
        raise RegraNegocio("Empresa de débito inválida.")
    return empresa


def _alerta(valor: Decimal) -> str | None:
    if valor > LIMITE_REFEICAO_DIA:
        return f"Acima do limite diário de refeição da política ({moeda(LIMITE_REFEICAO_DIA)})."
    return None


def _despesa(
    dados: DadosAlimentacao, arquivo: arquivos.ArquivoValidado, chave: str, agora: datetime
) -> Despesa:
    return Despesa(
        categoria="refeicao",
        data_despesa=dados.data_despesa,
        valor=dados.valor,
        arquivo_chave=chave,
        arquivo_nome=arquivo.nome,
        arquivo_tipo=arquivo.tipo,
        arquivo_tamanho=len(arquivo.conteudo),
        criado_em=agora,
    )


def _exigir(condicao: bool, mensagem: str) -> None:
    if not condicao:
        raise SemPermissao(mensagem)


def _exigir_status(sol: Solicitacao, esperado: str) -> None:
    if sol.status != esperado:
        raise RegraNegocio(
            f'Esta solicitação está "{ROTULO_STATUS.get(sol.status, sol.status)}"; '
            "a ação não se aplica mais."
        )
