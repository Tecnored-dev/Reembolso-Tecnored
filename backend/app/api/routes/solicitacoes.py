"""Solicitações de reembolso: criar, listar, ver, decidir, pagar, reenviar."""

from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.auth.deps import exigir_papel, usuario_atual
from app.auth.papeis import ADMIN
from app.auth.sessoes import Usuario
from app.config import ARQUIVO_TAMANHO_MAX, CATEGORIAS_VIAGEM, Settings, get_settings
from app.db import get_db
from app.models.solicitacao import Solicitacao
from app.services import arquivos as servico_arquivos
from app.services import fluxo
from app.services.erros import NaoEncontrado, RegraNegocio
from app.services.formatos import ler_valor
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
    valor: str = Field(max_length=20)
    descricao: str = Field(default="", max_length=200)
    arquivo: int | None = None  # posição em `arquivos`


_NOTAS = TypeAdapter(list[NotaViagem])


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
        "gestor_nome": sol.gestor_nome,
        "descricao": sol.descricao,
        "destino": sol.destino,
        "valor_total": str(sol.valor_total),
        "moeda": sol.moeda,
        "alerta_limite": sol.alerta_limite,
        "enviado_em": sol.enviado_em.isoformat(),
        "ultima_movimentacao_em": sol.ultima_movimentacao_em.isoformat(),
    }


def _completo(sol: Solicitacao, usuario: Usuario) -> dict:
    return {
        **_resumo(sol),
        "matricula": sol.matricula,
        "centro_custo": sol.centro_custo,
        "empresa": sol.empresa,
        "gestor_email": sol.gestor_email,
        "pula_gestor": sol.pula_gestor,
        "viagem_inicio": _iso(sol.viagem_inicio),
        "viagem_fim": _iso(sol.viagem_fim),
        "conferido_por": sol.conferido_por,
        "conferido_em": _iso(sol.conferido_em),
        "aprovado_por": sol.aprovado_por,
        "aprovado_em": _iso(sol.aprovado_em),
        "pago_por": sol.pago_por,
        "data_pagamento": _iso(sol.data_pagamento),
        "motivo_devolucao": sol.motivo_devolucao,
        "devolvido_por": sol.devolvido_por,
        "motivo_cancelamento": sol.motivo_cancelamento,
        "despesas": [
            {
                "id": d.id,
                "categoria": d.categoria,
                "categoria_rotulo": CATEGORIAS_VIAGEM.get(d.categoria, "Refeição"),
                "data_despesa": d.data_despesa.isoformat(),
                "valor": str(d.valor),
                "descricao": d.descricao,
                "arquivo_nome": d.arquivo_nome,
                "arquivo_tipo": d.arquivo_tipo,
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
    data_despesa: str, valor: str, descricao: str, empresa_id: int, gestor_email: str | None
) -> fluxo.DadosAlimentacao:
    try:
        data = date.fromisoformat(data_despesa)
    except ValueError:
        raise RegraNegocio("Data da despesa inválida.") from None
    return fluxo.DadosAlimentacao(
        data_despesa=data,
        valor=ler_valor(valor),
        descricao=descricao,
        empresa_id=empresa_id,
        gestor_email=(gestor_email or "").strip().lower() or None,
    )


async def _arquivo(upload: UploadFile | None) -> servico_arquivos.ArquivoValidado | None:
    if upload is None or not upload.filename:
        return None
    conteudo = await upload.read(ARQUIVO_TAMANHO_MAX + 1)
    return servico_arquivos.validar(conteudo, upload.filename)


def _datas(inicio: str, fim: str) -> tuple[date, date]:
    try:
        return date.fromisoformat(inicio), date.fromisoformat(fim)
    except ValueError:
        raise RegraNegocio("Datas da viagem inválidas.") from None


def _dados_viagem(
    destino: str,
    viagem_inicio: str,
    viagem_fim: str,
    descricao: str,
    empresa_id: int,
    gestor_email: str | None,
    despesas: str,
) -> fluxo.DadosViagem:
    try:
        notas = _NOTAS.validate_python(json.loads(despesas or "[]"))
    except (ValueError, ValidationError):
        raise RegraNegocio("Lista de notas inválida.") from None
    inicio, fim = _datas(viagem_inicio, viagem_fim)
    itens = []
    for n, nota in enumerate(notas, start=1):
        try:
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
            )
        )
    return fluxo.DadosViagem(
        destino=destino,
        inicio=inicio,
        fim=fim,
        descricao=descricao,
        empresa_id=empresa_id,
        gestor_email=(gestor_email or "").strip().lower() or None,
        itens=tuple(itens),
    )


async def _arquivos(uploads: list[UploadFile] | None) -> list[servico_arquivos.ArquivoValidado]:
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
    data_despesa: str = Form(...),
    valor: str = Form(...),
    descricao: str = Form(...),
    empresa_id: int = Form(...),
    gestor_email: str | None = Form(None),
    arquivo: UploadFile | None = File(None),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    armazenamento: Armazenamento = Depends(get_armazenamento),
):
    dados = _dados(data_despesa, valor, descricao, empresa_id, gestor_email)
    validado = await _arquivo(arquivo)
    if validado is None:
        raise RegraNegocio("Anexe a foto ou o PDF da nota.")
    sol = fluxo.criar_alimentacao(db, settings, armazenamento, usuario, dados, validado)
    return _completo(sol, usuario)


@router.post("/viagem", status_code=201)
async def criar_viagem(
    # Texto vazio chega como "campo ausente": o padrão "" deixa a mensagem
    # de validação do fluxo (em português) aparecer em vez do 422 genérico.
    destino: str = Form(""),
    viagem_inicio: str = Form(...),
    viagem_fim: str = Form(...),
    descricao: str = Form(""),
    empresa_id: int = Form(...),
    gestor_email: str | None = Form(None),
    despesas: str = Form(...),
    arquivos: list[UploadFile] = File([]),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    armazenamento: Armazenamento = Depends(get_armazenamento),
):
    dados = _dados_viagem(
        destino, viagem_inicio, viagem_fim, descricao, empresa_id, gestor_email, despesas
    )
    validados = await _arquivos(arquivos)
    sol = fluxo.criar_viagem(db, settings, armazenamento, usuario, dados, validados)
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
    if despesa is None:
        raise NaoEncontrado()
    try:
        conteudo = armazenamento.abrir(despesa.arquivo_chave)
    except ArquivoNaoEncontrado:
        raise NaoEncontrado() from None
    nome = despesa.arquivo_nome.replace('"', "")
    return Response(
        conteudo,
        media_type=despesa.arquivo_tipo,
        headers={
            "Content-Disposition": f'inline; filename="{nome}"',
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
    data_despesa: str = Form(...),
    valor: str = Form(...),
    descricao: str = Form(...),
    empresa_id: int = Form(...),
    gestor_email: str | None = Form(None),
    arquivo: UploadFile | None = File(None),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    armazenamento: Armazenamento = Depends(get_armazenamento),
):
    dados = _dados(data_despesa, valor, descricao, empresa_id, gestor_email)
    validado = await _arquivo(arquivo)
    sol = fluxo.reenviar(db, settings, armazenamento, usuario, sol_id, dados, validado)
    return _completo(sol, usuario)


@router.post("/{sol_id}/reenviar-viagem")
async def reenviar_viagem(
    sol_id: int,
    # Texto vazio chega como "campo ausente": o padrão "" deixa a mensagem
    # de validação do fluxo (em português) aparecer em vez do 422 genérico.
    destino: str = Form(""),
    viagem_inicio: str = Form(...),
    viagem_fim: str = Form(...),
    descricao: str = Form(""),
    empresa_id: int = Form(...),
    gestor_email: str | None = Form(None),
    despesas: str = Form(...),
    arquivos: list[UploadFile] = File([]),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    armazenamento: Armazenamento = Depends(get_armazenamento),
):
    dados = _dados_viagem(
        destino, viagem_inicio, viagem_fim, descricao, empresa_id, gestor_email, despesas
    )
    validados = await _arquivos(arquivos)
    sol = fluxo.reenviar_viagem(db, settings, armazenamento, usuario, sol_id, dados, validados)
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
