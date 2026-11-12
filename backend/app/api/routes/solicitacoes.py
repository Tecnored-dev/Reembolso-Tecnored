"""Solicitações: criar, listar, ver, decidir, pagar, reenviar e prestar contas."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.auth.deps import exigir_papel, usuario_atual
from app.auth.papeis import ADMIN
from app.auth.sessoes import Usuario
from app.config import (
    ARQUIVO_TAMANHO_MAX,
    CATEGORIA_KM,
    CATEGORIAS_ANTIGAS,
    CATEGORIAS_VIAGEM,
    LOCAIS_REFEICAO,
    MAX_DESPESAS_VIAGEM,
    VALOR_DIARIA,
    Settings,
    get_settings,
)
from app.db import get_db
from app.models.solicitacao import Solicitacao
from app.services import arquivos as servico_arquivos
from app.services import fluxo
from app.services.erros import NaoEncontrado, RegraNegocio
from app.services.formatos import ler_km, ler_valor
from app.storage import Armazenamento, ArquivoNaoEncontrado, get_armazenamento

router = APIRouter(prefix="/api/solicitacoes", tags=["solicitacoes"])


class Decisao(BaseModel):
    aprovar: bool
    comentario: str | None = Field(default=None, max_length=1000)


class Pagamento(BaseModel):
    data_pagamento: date


class NotaViagem(BaseModel):
    """Uma nota do reembolso de viagem, como vem do formulário (campo `despesas`)."""

    id: int | None = None
    categoria: str = Field(max_length=40)
    data_despesa: date
    # Vazio na quilometragem (o valor é calculado pelo servidor); nas outras notas,
    # vazio vira "Valor inválido".
    valor: str = Field(default="", max_length=20)
    descricao: str = Field(default="", max_length=200)
    arquivo: int | None = None  # posição em `arquivos`
    # Só na quilometragem: o valor é calculado (km x valor por km) e `valor` é ignorado.
    km: str = Field(default="", max_length=12)
    percurso: list[str] = Field(default_factory=list, max_length=20)


_NOTAS = TypeAdapter(list[NotaViagem])


class PedidoAdiantamento(BaseModel):
    # Texto vazio vira "" para a mensagem do fluxo (em português) aparecer.
    destino: str = Field(default="", max_length=200)
    viagem_inicio: date
    viagem_fim: date
    descricao: str = Field(default="", max_length=500)
    empresa_id: int
    gestor_email: str | None = Field(default=None, max_length=254)
    # Valor do adiantamento, ex. "250,00" (Thais, 15/10). Vazio vira erro em português.
    valor: str = Field(default="", max_length=20)
    # Pedido em nome de outra pessoa (opcional).
    beneficiario_email: str | None = Field(default=None, max_length=254)
    beneficiario_nome: str = Field(default="", max_length=200)
    beneficiario_matricula: str = Field(default="", max_length=30)

    def dados(self) -> fluxo.DadosAdiantamento:
        return fluxo.DadosAdiantamento(
            valor=ler_valor(self.valor) if self.valor.strip() else Decimal("0"),
            beneficiario=_beneficiario(
                self.beneficiario_email,
                self.beneficiario_nome,
                self.beneficiario_matricula,
            ),
            destino=self.destino,
            inicio=self.viagem_inicio,
            fim=self.viagem_fim,
            descricao=self.descricao,
            empresa_id=self.empresa_id,
            gestor_email=(self.gestor_email or "").strip().lower() or None,
        )


class LinhaPedidoDiaria(BaseModel):
    tipo: str = Field(default="", max_length=10)  # integral | parcial
    quantidade: int = Field(default=0, ge=0, le=1000)
    valor: str = Field(default="", max_length=20)  # só na parcial


class PedidoDiaria(BaseModel):
    """Diária de Viagem: linhas de valor integral/parcial, sem notas (Thais, 15/10)."""

    destino: str = Field(default="", max_length=200)
    viagem_inicio: date
    viagem_fim: date
    descricao: str = Field(default="", max_length=500)  # motivo da viagem
    empresa_id: int
    gestor_email: str | None = Field(default=None, max_length=254)
    centro_custo_id: str = Field(default="", max_length=10)
    internacional: bool = False
    linhas: list[LinhaPedidoDiaria] = Field(default_factory=list, max_length=50)
    beneficiario_email: str | None = Field(default=None, max_length=254)
    beneficiario_nome: str = Field(default="", max_length=200)
    beneficiario_matricula: str = Field(default="", max_length=30)

    def dados(self) -> fluxo.DadosDiaria:
        return fluxo.DadosDiaria(
            destino=self.destino,
            inicio=self.viagem_inicio,
            fim=self.viagem_fim,
            descricao=self.descricao,
            empresa_id=self.empresa_id,
            gestor_email=(self.gestor_email or "").strip().lower() or None,
            linhas=tuple(
                fluxo.ItemDiaria(
                    tipo=linha.tipo,
                    quantidade=linha.quantidade,
                    valor=ler_valor(linha.valor) if linha.valor.strip() else None,
                )
                for linha in self.linhas
            ),
            internacional=self.internacional,
            beneficiario=_beneficiario(
                self.beneficiario_email, self.beneficiario_nome, self.beneficiario_matricula
            ),
            centro_custo_id=_centro_custo_form(self.centro_custo_id),
        )


_ROTULO_COMPROVANTE = "Comprovante da devolução"


def _centro_custo_form(centro_custo_id: str) -> int | None:
    """Centro de custo do pedido (Thais, 15/10). Vazio = não informado."""
    try:
        return int(centro_custo_id) if centro_custo_id.strip() else None
    except ValueError:
        raise RegraNegocio("Centro de custo inválido.") from None


def _beneficiario(email: str | None, nome: str, matricula: str) -> fluxo.Beneficiario | None:
    """Pedido em nome de outra pessoa: só existe se o e-mail dela vier preenchido."""
    if not (email or "").strip():
        return None
    return fluxo.Beneficiario(email=email.strip(), nome=nome or "", matricula=matricula or "")


# ---------------------------------------------------------------------------
# Serialização
# ---------------------------------------------------------------------------
def _resumo(sol: Solicitacao) -> dict:
    return {
        "id": sol.id,
        "codigo": sol.codigo,
        "tipo": sol.tipo,
        "tipo_rotulo": fluxo.ROTULO_TIPO.get(sol.tipo, sol.tipo),
        "status": sol.status,
        "status_rotulo": fluxo.ROTULO_STATUS.get(sol.status, sol.status),
        "solicitante_nome": sol.solicitante_nome,
        "solicitante_email": sol.solicitante_email,
        # Preenchido só quando alguém pediu em nome do solicitante.
        "criado_por_nome": sol.criado_por_nome,
        "criado_por_email": sol.criado_por_email,
        "gestor_nome": sol.gestor_nome,
        "descricao": sol.descricao,
        "motivo": sol.motivo,
        "destino": sol.destino,
        "valor_total": str(sol.valor_total),
        "moeda": sol.moeda,
        "alerta_limite": sol.alerta_limite,
        "enviado_em": sol.enviado_em.isoformat(),
        "ultima_movimentacao_em": sol.ultima_movimentacao_em.isoformat(),
    }


def _completo(sol: Solicitacao, usuario: Usuario) -> dict:
    saldo = fluxo.saldo(sol)
    return {
        **_resumo(sol),
        "matricula": sol.matricula,
        "centro_custo": sol.centro_custo,
        "empresa": sol.empresa,
        "gestor_email": sol.gestor_email,
        "pula_gestor": sol.pula_gestor,
        "local_refeicao": sol.local_refeicao,
        "local_refeicao_rotulo": (
            LOCAIS_REFEICAO[sol.local_refeicao][0]
            if sol.local_refeicao in LOCAIS_REFEICAO
            else None
        ),
        "viagem_inicio": _iso(sol.viagem_inicio),
        "viagem_fim": _iso(sol.viagem_fim),
        "viagem_internacional": sol.viagem_internacional,
        "linhas_diaria": [
            {
                "id": linha.id,
                "tipo": linha.tipo,
                "tipo_rotulo": (
                    "Valor Integral" if linha.tipo == fluxo.DIARIA_INTEGRAL else "Valor Parcial"
                ),
                "quantidade": linha.quantidade,
                "valor_unitario": str(linha.valor_unitario),
                "subtotal": str(linha.valor_unitario * linha.quantidade),
            }
            for linha in sol.linhas_diaria
        ],
        "diarias": sol.diarias,
        "diaria_complementar": bool(sol.diaria_complementar),
        "valor_complementar": (
            None if sol.valor_complementar is None else str(sol.valor_complementar)
        ),
        "prazo_prestacao": _iso(fluxo.prazo_prestacao(sol)),
        "valor_diaria": str(VALOR_DIARIA) if sol.tipo == fluxo.TIPO_ADIANTAMENTO else None,
        "valor_gasto": None if sol.valor_gasto is None else str(sol.valor_gasto),
        "saldo": None if saldo is None else str(saldo),
        "prestacao_enviada_em": _iso(sol.prestacao_enviada_em),
        "prestacao_conferida_por": sol.prestacao_conferida_por,
        "devolucao_confirmada_por": sol.devolucao_confirmada_por,
        "diferenca_aprovada_por": sol.diferenca_aprovada_por,
        "data_pagamento_diferenca": _iso(sol.data_pagamento_diferenca),
        "encerrado_em": _iso(sol.encerrado_em),
        "conferido_por": sol.conferido_por,
        "conferido_em": _iso(sol.conferido_em),
        "aprovado_por": sol.aprovado_por,
        "aprovado_em": _iso(sol.aprovado_em),
        "pago_por": sol.pago_por,
        "data_pagamento": _iso(sol.data_pagamento),
        "motivo_devolucao": sol.motivo_devolucao,
        "devolvido_por": sol.devolvido_por,
        "recusado_por": sol.recusado_por,
        "recusado_em": _iso(sol.recusado_em),
        "motivo_recusa": sol.motivo_recusa,
        "motivo_cancelamento": sol.motivo_cancelamento,
        "despesas": [
            {
                "id": d.id,
                "categoria": d.categoria,
                "categoria_rotulo": (
                    _ROTULO_COMPROVANTE
                    if d.categoria == fluxo.COMPROVANTE_DEVOLUCAO
                    else "Despesas diversas"
                    if d.categoria == fluxo.CATEGORIA_DIVERSAS
                    else CATEGORIAS_VIAGEM.get(d.categoria)
                    or CATEGORIAS_ANTIGAS.get(d.categoria, d.categoria)
                ),
                "data_despesa": d.data_despesa.isoformat(),
                "valor": str(d.valor),
                "descricao": d.descricao,
                "arquivo_nome": d.arquivo_nome,
                "arquivo_tipo": d.arquivo_tipo,
                "km": str(d.km) if d.km is not None else None,
                "percurso": json.loads(d.percurso) if d.percurso else None,
            }
            for d in sol.despesas
        ],
        "historico": [
            {
                "acao": h.acao,
                "status_para": h.status_para,
                "status_rotulo": fluxo.ROTULO_STATUS.get(h.status_para, h.status_para),
                "usuario_nome": h.usuario_nome,
                "comentario": h.comentario,
                "criado_em": h.criado_em.isoformat(),
            }
            for h in sol.historico
        ],
        "acoes": fluxo.acoes_disponiveis(sol, usuario),
    }


def _iso(valor) -> str | None:
    return valor.isoformat() if valor else None


# ---------------------------------------------------------------------------
# Entrada de formulário (multipart, por causa do arquivo)
# ---------------------------------------------------------------------------
def _dados(
    descricao: str,
    empresa_id: int,
    gestor_email: str | None,
    motivo: str,
    despesas: str,
    centro_custo_id: str = "",
) -> fluxo.DadosDespesas:
    """Reembolso de despesas (alimentação ou diversas): notas como na viagem."""
    return fluxo.DadosDespesas(
        descricao=descricao,
        empresa_id=empresa_id,
        gestor_email=(gestor_email or "").strip().lower() or None,
        itens=_itens(despesas),
        motivo=motivo.strip(),
        centro_custo_id=_centro_custo_form(centro_custo_id),
    )


async def _arquivo(upload: UploadFile | None) -> servico_arquivos.ArquivoValidado | None:
    if upload is None or not upload.filename:
        return None
    conteudo = await upload.read(ARQUIVO_TAMANHO_MAX + 1)
    return servico_arquivos.validar(conteudo, upload.filename)


def _itens(despesas: str) -> tuple[fluxo.ItemViagem, ...]:
    try:
        notas = _NOTAS.validate_python(json.loads(despesas or "[]"))
    except (ValueError, ValidationError):
        raise RegraNegocio("Lista de notas inválida.") from None
    itens = []
    for n, nota in enumerate(notas, start=1):
        km = None
        erro_km = None
        try:
            if nota.categoria == CATEGORIA_KM:
                try:
                    km = ler_km(nota.km)
                    valor = fluxo.valor_km(km)
                except RegraNegocio as erro:
                    # O fluxo dá a mensagem depois de conferir a categoria.
                    erro_km, valor = str(erro), Decimal("0.00")
            else:
                valor = ler_valor(nota.valor)
        except RegraNegocio as erro:
            raise RegraNegocio(f"Nota {n}: {erro}") from None
        itens.append(
            fluxo.ItemViagem(
                categoria=nota.categoria,
                data_despesa=nota.data_despesa,
                valor=valor,
                descricao=nota.descricao,
                arquivo=nota.arquivo,
                id=nota.id,
                km=km,
                percurso=tuple(nota.percurso),
                erro_km=erro_km,
            )
        )
    return tuple(itens)


async def _arquivos(uploads: list[UploadFile] | None) -> list[servico_arquivos.ArquivoValidado]:
    # Conta antes de ler: cada arquivo vai para a memória (até 10 MB), então um
    # envio com centenas de arquivos derrubaria o container.
    if len(uploads or []) > MAX_DESPESAS_VIAGEM:
        raise RegraNegocio(f"Máximo de {MAX_DESPESAS_VIAGEM} arquivos por envio.")
    validados = []
    for n, upload in enumerate(uploads or [], start=1):
        if not upload.filename:
            continue
        conteudo = await upload.read(ARQUIVO_TAMANHO_MAX + 1)
        try:
            validados.append(servico_arquivos.validar(conteudo, upload.filename))
        except RegraNegocio as erro:
            raise RegraNegocio(f"Arquivo {n} ({upload.filename}): {erro}") from None
    return validados


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------
@router.get("")
def listar(
    escopo: str = "minhas",
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    return [_resumo(s) for s in fluxo.listar(db, usuario, escopo)]


@router.post("/alimentacao", status_code=201)
async def criar_alimentacao(
    # Texto vazio chega como "campo ausente": o padrão "" deixa a mensagem
    # de validação do fluxo (em português) aparecer em vez do 422 genérico.
    descricao: str = Form(""),
    empresa_id: int = Form(...),
    gestor_email: str | None = Form(None),
    motivo: str = Form(""),
    despesas: str = Form(...),
    centro_custo_id: str = Form(""),
    # Pedido em nome de outra pessoa (opcional; só o e-mail liga a opção).
    beneficiario_email: str = Form(""),
    beneficiario_nome: str = Form(""),
    beneficiario_matricula: str = Form(""),
    arquivos: list[UploadFile] = File([]),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    armazenamento: Armazenamento = Depends(get_armazenamento),
):
    """Reembolso de despesas - alimentação: notas com categoria (Thais, 15/10)."""
    dados = replace(
        _dados(descricao, empresa_id, gestor_email, motivo, despesas, centro_custo_id),
        beneficiario=_beneficiario(beneficiario_email, beneficiario_nome, beneficiario_matricula),
    )
    validados = await _arquivos(arquivos)
    sol = fluxo.criar_alimentacao(
        db, settings, armazenamento, usuario, dados, validados, fluxo.TIPO_ALIMENTACAO
    )
    return _completo(sol, usuario)


@router.post("/diversas", status_code=201)
async def criar_diversas(
    descricao: str = Form(""),
    empresa_id: int = Form(...),
    gestor_email: str | None = Form(None),
    motivo: str = Form(""),
    despesas: str = Form(...),
    centro_custo_id: str = Form(""),
    beneficiario_email: str = Form(""),
    beneficiario_nome: str = Form(""),
    beneficiario_matricula: str = Form(""),
    arquivos: list[UploadFile] = File([]),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    armazenamento: Armazenamento = Depends(get_armazenamento),
):
    """Reembolso de despesas - diversas: notas sem categoria (corrige em /reenviar)."""
    dados = replace(
        _dados(descricao, empresa_id, gestor_email, motivo, despesas, centro_custo_id),
        beneficiario=_beneficiario(beneficiario_email, beneficiario_nome, beneficiario_matricula),
    )
    validados = await _arquivos(arquivos)
    sol = fluxo.criar_alimentacao(
        db, settings, armazenamento, usuario, dados, validados, fluxo.TIPO_DIVERSAS
    )
    return _completo(sol, usuario)


@router.post("/viagem", status_code=201)
def criar_diaria(
    pedido: PedidoDiaria,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Diária de Viagem (Thais, 15/10): linhas integral/parcial, sem notas."""
    sol = fluxo.criar_diaria(db, settings, usuario, pedido.dados())
    return _completo(sol, usuario)


@router.post("/adiantamento", status_code=201)
def criar_adiantamento(
    pedido: PedidoAdiantamento,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    sol = fluxo.criar_adiantamento(db, settings, usuario, pedido.dados())
    return _completo(sol, usuario)


@router.get("/{sol_id}")
def ver(sol_id: int, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    return _completo(fluxo.obter(db, usuario, sol_id), usuario)


@router.get("/{sol_id}/despesas/{despesa_id}/arquivo")
def baixar_arquivo(
    sol_id: int,
    despesa_id: int,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    armazenamento: Armazenamento = Depends(get_armazenamento),
):
    sol = fluxo.obter(db, usuario, sol_id)
    despesa = next((d for d in sol.despesas if d.id == despesa_id), None)
    if despesa is None or not despesa.arquivo_chave:  # quilometragem não tem arquivo
        raise NaoEncontrado()
    try:
        conteudo = armazenamento.abrir(despesa.arquivo_chave)
    except ArquivoNaoEncontrado:
        raise NaoEncontrado() from None
    nome = despesa.arquivo_nome or "nota"
    # Cabeçalho HTTP é latin-1: nome ASCII de reserva + filename* em UTF-8 (RFC 6266),
    # senão um nome com emoji ou travessão derruba o download com erro 500.
    ascii_nome = nome.encode("ascii", "replace").decode().replace('"', "").replace("?", "_")
    return Response(
        conteudo,
        media_type=despesa.arquivo_tipo,
        headers={
            "Content-Disposition": (
                f"inline; filename=\"{ascii_nome}\"; filename*=UTF-8''{quote(nome, safe='')}"
            ),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/{sol_id}/conferir")
def conferir(
    sol_id: int,
    decisao: Decisao,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    sol = fluxo.conferir(db, settings, usuario, sol_id, decisao.aprovar, decisao.comentario)
    return _completo(sol, usuario)


@router.post("/{sol_id}/aprovar")
def aprovar(
    sol_id: int,
    decisao: Decisao,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    sol = fluxo.decidir_gestor(db, settings, usuario, sol_id, decisao.aprovar, decisao.comentario)
    return _completo(sol, usuario)


@router.post("/{sol_id}/pagar")
def pagar(
    sol_id: int,
    pagamento: Pagamento,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    sol = fluxo.pagar(db, settings, usuario, sol_id, pagamento.data_pagamento)
    return _completo(sol, usuario)


@router.post("/{sol_id}/reenviar")
async def reenviar(
    sol_id: int,
    descricao: str = Form(""),
    empresa_id: int = Form(...),
    gestor_email: str | None = Form(None),
    motivo: str = Form(""),
    despesas: str = Form(...),
    centro_custo_id: str = Form(""),
    arquivos: list[UploadFile] = File([]),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    armazenamento: Armazenamento = Depends(get_armazenamento),
):
    dados = _dados(descricao, empresa_id, gestor_email, motivo, despesas, centro_custo_id)
    validados = await _arquivos(arquivos)
    sol = fluxo.reenviar(db, settings, armazenamento, usuario, sol_id, dados, validados)
    return _completo(sol, usuario)


@router.post("/{sol_id}/reenviar-viagem")
def reenviar_diaria(
    sol_id: int,
    pedido: PedidoDiaria,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    sol = fluxo.reenviar_diaria(db, settings, usuario, sol_id, pedido.dados())
    return _completo(sol, usuario)


@router.post("/{sol_id}/reenviar-adiantamento")
def reenviar_adiantamento(
    sol_id: int,
    pedido: PedidoAdiantamento,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    sol = fluxo.reenviar_adiantamento(db, settings, usuario, sol_id, pedido.dados())
    return _completo(sol, usuario)


@router.post("/{sol_id}/prestacao")
async def prestar_contas(
    sol_id: int,
    despesas: str = Form(...),
    arquivos: list[UploadFile] = File([]),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    armazenamento: Armazenamento = Depends(get_armazenamento),
):
    itens = _itens(despesas)
    validados = await _arquivos(arquivos)
    sol = fluxo.enviar_prestacao(db, settings, armazenamento, usuario, sol_id, itens, validados)
    return _completo(sol, usuario)


@router.post("/{sol_id}/comprovante")
async def enviar_comprovante(
    sol_id: int,
    data_transferencia: str = Form(...),
    arquivo: UploadFile | None = File(None),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    armazenamento: Armazenamento = Depends(get_armazenamento),
):
    try:
        data = date.fromisoformat(data_transferencia)
    except ValueError:
        raise RegraNegocio("Data da transferência inválida.") from None
    validado = await _arquivo(arquivo)
    if validado is None:
        raise RegraNegocio("Anexe o comprovante da transferência.")
    sol = fluxo.enviar_comprovante(db, settings, armazenamento, usuario, sol_id, data, validado)
    return _completo(sol, usuario)


@router.post("/{sol_id}/confirmar-devolucao")
def confirmar_devolucao(
    sol_id: int,
    decisao: Decisao,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    sol = fluxo.confirmar_devolucao(
        db, settings, usuario, sol_id, decisao.aprovar, decisao.comentario
    )
    return _completo(sol, usuario)


tarefas = APIRouter(prefix="/api/tarefas", tags=["tarefas"])


@tarefas.post("/expiracao")
def rodar_expiracao(
    usuario: Usuario = Depends(exigir_papel(ADMIN)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Roda já a expiração das devolvidas (normalmente roda sozinha a cada hora)."""
    return fluxo.processar_expiracoes(db, settings)
