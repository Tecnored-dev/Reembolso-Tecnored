"""Painel de teste ("Ver como"): usuários de teste, dados de demonstração e limpeza.

Só existe com PAINEL_TESTE_ENABLED e fora da `main` (Settings.validar). Os
usuários de teste usam um domínio que não existe (`.invalid`), então nenhum
e-mail de aviso chega a ninguém de verdade, e os pedidos de teste ficam
separados dos reais: quem é de teste só enxerga pedidos de teste, e quem é real
nunca vê pedido de teste (ver `eh_teste` em fluxo, gestores e notificações).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.auth.papeis import ADMIN, FINANCEIRO, GESTOR
from app.auth.sessoes import Usuario, agora_utc
from app.config import Settings
from app.models.cadastros import CentroCusto, Empresa
from app.models.cadastros import Usuario as CadastroUsuario
from app.models.solicitacao import Notificacao, Solicitacao
from app.services import arquivos, fluxo
from app.services.erros import RegraNegocio
from app.services.isolamento import DOMINIO_TESTE, eh_teste
from app.storage.base import Armazenamento

VIA_TESTE = "teste"
COOKIE_ADMIN = "session_admin"


@dataclass(frozen=True)
class UsuarioTeste:
    chave: str
    email: str
    nome: str
    papeis: tuple[str, ...]
    descricao: str


USUARIOS_TESTE: tuple[UsuarioTeste, ...] = (
    UsuarioTeste(
        "colaborador",
        f"teste.colaborador{DOMINIO_TESTE}",
        "Colaborador Teste",
        (),
        "Pede reembolso, diária e adiantamento",
    ),
    UsuarioTeste(
        "gestor",
        f"teste.gestor{DOMINIO_TESTE}",
        "Gestor Teste",
        (GESTOR,),
        "Aprova ou recusa os pedidos que chegam para ele",
    ),
    UsuarioTeste(
        "financeiro",
        f"teste.financeiro{DOMINIO_TESTE}",
        "Financeiro Teste",
        (FINANCEIRO,),
        "Confere, devolve e registra o pagamento",
    ),
)
_POR_EMAIL = {u.email: u for u in USUARIOS_TESTE}
MATRICULA_TESTE = "T-0001"


def usuario_teste(email: str) -> UsuarioTeste | None:
    return _POR_EMAIL.get((email or "").strip().lower())


def eh_admin(usuario: Usuario, settings: Settings) -> bool:
    """Admin do painel: grupo admin do Azure ou e-mail em PAINEL_TESTE_ADMINS.
    Usuário de teste nunca é admin."""
    if usuario.via == VIA_TESTE or eh_teste(usuario.email):
        return False
    return usuario.tem(ADMIN) or usuario.email in settings.admins_painel_teste


def para_sessao(u: UsuarioTeste) -> Usuario:
    return Usuario(email=u.email, nome=u.nome, papeis=u.papeis, via=VIA_TESTE)


def garantir_cadastros(db: Session) -> None:
    """Usuários de teste já com matrícula e centro de custo (não passam pelo perfil)."""
    centro = db.scalar(select(CentroCusto).where(CentroCusto.ativo).order_by(CentroCusto.codigo))
    agora = agora_utc()
    for u in USUARIOS_TESTE:
        cadastro = db.scalar(select(CadastroUsuario).where(CadastroUsuario.email == u.email))
        if cadastro is None:
            cadastro = CadastroUsuario(email=u.email, nome=u.nome, criado_em=agora)
            db.add(cadastro)
        cadastro.nome = u.nome
        cadastro.papeis = ",".join(u.papeis)
        cadastro.matricula = cadastro.matricula or MATRICULA_TESTE
        if centro and cadastro.centro_custo_id is None:
            cadastro.centro_custo_id = centro.id
        cadastro.atualizado_em = agora
    db.flush()


# ---------------------------------------------------------------------------
# Limpeza
# ---------------------------------------------------------------------------
def limpar(db: Session, armazenamento: Armazenamento) -> int:
    """Apaga só os pedidos de usuários de teste (e os arquivos das notas)."""
    sols = db.scalars(
        select(Solicitacao).where(
            or_(
                Solicitacao.solicitante_email.like(f"%{DOMINIO_TESTE}"),
                Solicitacao.criado_por_email.like(f"%{DOMINIO_TESTE}"),
            )
        )
    ).all()
    ids = [s.id for s in sols]
    for sol in sols:
        for despesa in sol.despesas:
            armazenamento.remover(despesa.arquivo_chave)
    if ids:
        db.execute(delete(Notificacao).where(Notificacao.solicitacao_id.in_(ids)))
        for sol in sols:
            db.delete(sol)  # cascade: notas, linhas de diária e histórico
    db.commit()
    return len(ids)


# ---------------------------------------------------------------------------
# Dados de demonstração
# ---------------------------------------------------------------------------
# PNG 1x1 válido: serve de "foto da nota" nos pedidos de demonstração.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360f8cfc00000030101009f5d63d00000000049454e44ae426082"
)


def _nota(
    categoria: str, dias_atras: int, valor: str, descricao: str, arquivo: int = 0
) -> fluxo.ItemViagem:
    return fluxo.ItemViagem(
        categoria=categoria,
        data_despesa=date.today() - timedelta(days=dias_atras),
        valor=Decimal(valor),
        descricao=descricao,
        arquivo=arquivo,
    )


def criar_demo(db: Session, settings: Settings, armazenamento: Armazenamento) -> list[Solicitacao]:
    """Um pedido de cada tipo em cada etapa, para a apresentação. Quem age é o
    usuário de teste certo em cada passo, pelas mesmas regras do sistema."""
    garantir_cadastros(db)
    db.commit()
    colab, gestor, fin = (para_sessao(u) for u in USUARIOS_TESTE)
    empresa = db.scalar(select(Empresa).where(Empresa.ativo).order_by(Empresa.id))
    centro = db.scalar(select(CentroCusto).where(CentroCusto.ativo).order_by(CentroCusto.codigo))
    if empresa is None or centro is None:
        raise RegraNegocio("Faltam empresa e centro de custo cadastrados.")
    arquivo = arquivos.validar(_PNG, "nota-demo.png")
    emails = {"gestor": gestor.email}
    ini = date.today() + timedelta(days=7)
    fim = ini + timedelta(days=2)
    criados: list[Solicitacao] = []

    def despesas(tipo, itens, descricao, motivo):
        sol = fluxo.criar_alimentacao(
            db,
            settings,
            armazenamento,
            colab,
            fluxo.DadosDespesas(
                descricao=descricao,
                empresa_id=empresa.id,
                gestor_email=emails["gestor"],
                itens=itens,
                motivo=motivo,
                centro_custo_id=centro.id,
            ),
            [arquivo] * len(itens),  # cada nota tem o seu arquivo
            tipo=tipo,
        )
        criados.append(sol)
        return sol

    def diaria(linhas, destino, motivo):
        sol = fluxo.criar_diaria(
            db,
            settings,
            colab,
            fluxo.DadosDiaria(
                destino=destino,
                inicio=ini,
                fim=fim,
                descricao=motivo,
                empresa_id=empresa.id,
                gestor_email=emails["gestor"],
                linhas=linhas,
                centro_custo_id=centro.id,
            ),
        )
        criados.append(sol)
        return sol

    def adiantamento(valor, destino):
        sol = fluxo.criar_adiantamento(
            db,
            settings,
            colab,
            fluxo.DadosAdiantamento(
                destino=destino,
                inicio=ini,
                fim=fim,
                descricao="Viagem a trabalho (demonstração)",
                empresa_id=empresa.id,
                gestor_email=emails["gestor"],
                valor=Decimal(valor),
            ),
        )
        criados.append(sol)
        return sol

    hoje = date.today()
    integral = fluxo.ItemDiaria(fluxo.DIARIA_INTEGRAL, 2)
    parcial = fluxo.ItemDiaria(fluxo.DIARIA_PARCIAL, 1, Decimal("80.00"))

    # 1) Pendente de conferência (alimentação)
    despesas(
        fluxo.TIPO_ALIMENTACAO,
        (_nota("refeicao", 1, "38.50", "Almoço com cliente"),),
        "Almoço (demonstração)",
        "Reunião comercial",
    )
    # 2) Pendente de conferência (diária)
    diaria((integral, parcial), "Campinas - SP", "Visita ao cliente (demonstração)")
    # 3) Devolvido para correção
    sol = despesas(
        fluxo.TIPO_ALIMENTACAO,
        (_nota("refeicao", 2, "52.00", "Jantar"),),
        "Jantar (demonstração)",
        "Trabalho externo",
    )
    fluxo.conferir(db, settings, fin, sol.id, False, "Falta o CNPJ legível na nota.")
    # 4) Pendente de aprovação (despesas diversas, 2 notas)
    sol = despesas(
        fluxo.TIPO_DIVERSAS,
        (
            _nota("diversos", 3, "89.90", "Carregador de celular"),
            _nota("diversos", 3, "25.00", "Créditos de celular", arquivo=1),
        ),
        "Itens de trabalho (demonstração)",
        "Outros",
    )
    fluxo.conferir(db, settings, fin, sol.id, True, None)
    # 5) Adiantamento aguardando aprovação do gestor
    adiantamento("1500.00", "Rio de Janeiro - RJ")
    # 6) Aguardando pagamento (diária aprovada)
    sol = diaria((integral,), "Marabá - PA", "Inspeção de equipamentos (demonstração)")
    fluxo.conferir(db, settings, fin, sol.id, True, None)
    fluxo.decidir_gestor(db, settings, gestor, sol.id, True, None)
    # 7) Adiantamento pago, aguardando prestação de contas
    sol = adiantamento("900.00", "Belo Horizonte - MG")
    fluxo.decidir_gestor(db, settings, gestor, sol.id, True, None)
    fluxo.pagar(db, settings, fin, sol.id, hoje)
    # 8) Finalizado - Pago
    sol = despesas(
        fluxo.TIPO_ALIMENTACAO,
        (_nota("refeicao", 4, "31.00", "Almoço"),),
        "Almoço (demonstração)",
        "Treinamento",
    )
    fluxo.conferir(db, settings, fin, sol.id, True, None)
    fluxo.decidir_gestor(db, settings, gestor, sol.id, True, None)
    fluxo.pagar(db, settings, fin, sol.id, hoje)
    # 9) Finalizado - Recusado
    sol = despesas(
        fluxo.TIPO_DIVERSAS,
        (_nota("diversos", 5, "240.00", "Compra sem autorização"),),
        "Compra (demonstração)",
        "Outros",
    )
    fluxo.conferir(db, settings, fin, sol.id, True, None)
    fluxo.decidir_gestor(db, settings, gestor, sol.id, False, "Compra não autorizada.")
    return criados
