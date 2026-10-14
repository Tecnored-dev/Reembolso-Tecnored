"""Perfil do usuário, listas de apoio (centros de custo, empresas) e gestores."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import usuario_atual
from app.auth.papeis import GESTOR
from app.auth.sessoes import Usuario, agora_utc
from app.config import (
    CATEGORIAS_VIAGEM,
    LIMITE_REFEICAO_DIA,
    LIMITE_SOLICITACAO,
    LOCAIS_REFEICAO,
    MAX_DIARIAS,
    MOTIVOS,
    VALOR_DIARIA,
    Settings,
    get_settings,
)
from app.db import get_db
from app.models.cadastros import CentroCusto, Empresa
from app.models.cadastros import Usuario as CadastroUsuario
from app.services import gestores
from app.services.erros import RegraNegocio

router = APIRouter(prefix="/api", tags=["cadastros"])


class PerfilEntrada(BaseModel):
    matricula: str = Field(min_length=1, max_length=30)
    centro_custo_id: int


def _perfil(db: Session, usuario: Usuario) -> CadastroUsuario:
    cadastro = db.scalar(select(CadastroUsuario).where(CadastroUsuario.email == usuario.email))
    if cadastro is None:  # sessão anterior ao cadastro existir (não deveria acontecer)
        agora = agora_utc()
        cadastro = CadastroUsuario(
            email=usuario.email,
            nome=usuario.nome,
            papeis=",".join(usuario.papeis),
            criado_em=agora,
            atualizado_em=agora,
        )
        db.add(cadastro)
        db.flush()
    return cadastro


def _saida_perfil(cadastro: CadastroUsuario) -> dict:
    cc = cadastro.centro_custo
    return {
        "email": cadastro.email,
        "nome": cadastro.nome,
        "matricula": cadastro.matricula,
        "centro_custo": {"id": cc.id, "rotulo": cc.rotulo} if cc else None,
        "completo": cadastro.perfil_completo,
    }


@router.get("/perfil")
def ver_perfil(usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    cadastro = _perfil(db, usuario)
    db.commit()
    return _saida_perfil(cadastro)


@router.put("/perfil")
def salvar_perfil(
    entrada: PerfilEntrada,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    centro = db.get(CentroCusto, entrada.centro_custo_id)
    if centro is None or not centro.ativo:
        raise RegraNegocio("Centro de custo inválido.")
    matricula = entrada.matricula.strip()
    if not matricula:
        raise RegraNegocio("Informe a matrícula.")
    cadastro = _perfil(db, usuario)
    cadastro.matricula = matricula
    cadastro.centro_custo_id = centro.id
    cadastro.atualizado_em = agora_utc()
    db.commit()
    db.refresh(cadastro)
    return _saida_perfil(cadastro)


@router.get("/cadastros")
def cadastros(usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    centros = db.scalars(
        select(CentroCusto).where(CentroCusto.ativo).order_by(CentroCusto.codigo)
    ).all()
    empresas = db.scalars(select(Empresa).where(Empresa.ativo).order_by(Empresa.nome)).all()
    return {
        "centros_custo": [{"id": c.id, "rotulo": c.rotulo} for c in centros],
        "empresas": [{"id": e.id, "nome": e.nome} for e in empresas],
        "limite_refeicao_dia": str(LIMITE_REFEICAO_DIA),
        "limite_solicitacao": str(LIMITE_SOLICITACAO),
        "categorias_viagem": [{"id": k, "rotulo": v} for k, v in CATEGORIAS_VIAGEM.items()],
        "valor_diaria": str(VALOR_DIARIA),
        "motivos": MOTIVOS,
        "locais_refeicao": [
            {"id": chave, "rotulo": rotulo, "limite": str(limite)}
            for chave, (rotulo, limite) in LOCAIS_REFEICAO.items()
        ],
        "max_diarias": MAX_DIARIAS,
    }


@router.get("/gestores")
def listar_gestores(
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Gestores para escolher — sem o próprio usuário (ninguém aprova a si mesmo)."""
    return [
        {"email": g.email, "nome": g.nome}
        for g in gestores.listar(db, settings)
        if g.email != usuario.email
    ]


@router.get("/usuarios")
def buscar_usuarios(
    busca: str = "",
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Colegas que já entraram no sistema, para pedir em nome de outra pessoa.

    Quem nunca entrou não aparece aqui (falta a permissão `User.ReadBasic.All`
    para ler o Azure); nesse caso o formulário pede e-mail, nome, matrícula e
    centro de custo.
    """
    termo = busca.strip().lower()
    if len(termo) < 2:
        return []
    padrao = f"%{termo}%"
    encontrados = db.scalars(
        select(CadastroUsuario)
        .where(
            CadastroUsuario.email != usuario.email,
            (CadastroUsuario.email.ilike(padrao)) | (CadastroUsuario.nome.ilike(padrao)),
        )
        .order_by(CadastroUsuario.nome)
        .limit(15)
    ).all()
    emails_gestores = {g.email for g in gestores.listar(db, settings)}
    return [
        {
            "email": u.email,
            "nome": u.nome,
            "perfil_completo": u.perfil_completo,
            "eh_gestor": GESTOR in u.lista_papeis or u.email in emails_gestores,
        }
        for u in encontrados
    ]
