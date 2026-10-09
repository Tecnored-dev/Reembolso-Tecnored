"""Configuração da aplicação.

Constantes de conteúdo ficam aqui no código (versionadas); o que muda por
ambiente vem de variáveis de ambiente (.env local ou Environment Variables do
Dokploy) — mesmo padrão do Hello-World. Nunca commitar valores reais.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

# ---------------------------------------------------------------------------
# Conteúdo (edite aqui e faça commit — o CI/CD aplica)
# ---------------------------------------------------------------------------
APP_TITLE = "Reembolso"
APP_WELCOME_MESSAGE = "Reembolso de alimentação e viagem — Tecnored"
SESSION_DURATION_HOURS = 8

# Regras de negócio (decididas com a Thais — ver docs do projeto)
LIMITE_REFEICAO_DIA = Decimal("135.00")  # política: só ALERTA, não bloqueia
DIAS_LEMBRETE_DEVOLVIDO = 5  # lembrete ao colaborador com solicitação devolvida parada
DIAS_EXPIRACAO_DEVOLVIDO = 7  # depois disso, cancela
ARQUIVO_TAMANHO_MAX = 10 * 1024 * 1024  # 10 MB por nota
LIMITE_SOLICITACAO = Decimal("5000.00")  # total por solicitação: só ALERTA, não bloqueia
MAX_DESPESAS_VIAGEM = 30  # notas por reembolso de viagem

# Categorias das despesas de viagem (chave gravada no banco → rótulo na tela).
# Os limites de hospedagem, translado e lavanderia ainda NÃO geram alerta: falta
# a Thais confirmar a unidade de cada um (por diária? por viagem? por semana?).
CATEGORIAS_VIAGEM = {
    "refeicao": "Refeição",
    "hospedagem": "Hospedagem",
    "transporte": "Transporte / translado",
    "lavanderia": "Lavanderia, internet e telefone",
    "outros": "Outros",
}

AMBIENTES = ("local", "hml", "main")


def _bool(nome: str, padrao: str = "false") -> bool:
    return os.environ.get(nome, padrao).strip().lower() in {"1", "true", "yes", "on"}


def _ler(arquivo: str) -> str | None:
    caminho = Path(__file__).resolve().parent.parent / arquivo
    return caminho.read_text().strip() if caminho.exists() else None


@dataclass(frozen=True)
class Settings:
    app_env: str = field(default_factory=lambda: os.environ.get("APP_ENV", "local"))
    db_url: str = field(default_factory=lambda: os.environ.get("DB_URL", ""))

    # Azure AD (OIDC). Vazios = login Microsoft indisponível (a API sobe mesmo
    # assim, para dar para trabalhar antes do App Registration existir).
    azure_client_id: str = field(default_factory=lambda: os.environ.get("AZURE_CLIENT_ID", ""))
    azure_client_secret: str = field(
        default_factory=lambda: os.environ.get("AZURE_CLIENT_SECRET", "")
    )
    azure_tenant_id: str = field(default_factory=lambda: os.environ.get("AZURE_TENANT_ID", ""))
    azure_redirect_uri: str = field(
        default_factory=lambda: os.environ.get(
            "AZURE_REDIRECT_URI", "http://localhost:8081/auth/callback"
        )
    )
    azure_login_prompt: str = field(
        default_factory=lambda: os.environ.get("AZURE_LOGIN_PROMPT", "select_account")
    )

    # Object IDs dos grupos de segurança (Azure AD). Quem não está em nenhum é
    # "colaborador" — liberado para todo usuário do domínio (ok da TI, 29/09).
    grupo_gestor: str = field(default_factory=lambda: os.environ.get("AZURE_GROUP_GESTOR", ""))
    grupo_financeiro: str = field(
        default_factory=lambda: os.environ.get("AZURE_GROUP_FINANCEIRO", "")
    )
    grupo_admin: str = field(default_factory=lambda: os.environ.get("AZURE_GROUP_ADMIN", ""))

    cf_access_team_domain: str = field(
        default_factory=lambda: os.environ.get("CF_ACCESS_TEAM_DOMAIN", "")
    )
    frontend_url: str = field(
        default_factory=lambda: os.environ.get("FRONTEND_URL", "http://localhost:8080")
    )
    app_bg_color: str = field(default_factory=lambda: os.environ.get("APP_BG_COLOR", "#32746a"))
    enable_api_docs: bool = field(default_factory=lambda: _bool("ENABLE_API_DOCS"))

    # Login de desenvolvimento (sem Microsoft) — SÓ com APP_ENV=local.
    dev_login_enabled: bool = field(default_factory=lambda: _bool("DEV_LOGIN_ENABLED"))

    # Armazenamento dos arquivos das notas. "local" = pasta no volume /data.
    # S3 ou SharePoint entram quando a TI decidir (camada em app/storage).
    storage_backend: str = field(default_factory=lambda: os.environ.get("STORAGE_BACKEND", "local"))
    storage_local_dir: str = field(
        default_factory=lambda: os.environ.get("STORAGE_LOCAL_DIR", "/data/arquivos")
    )

    # Tarefas periódicas (expiração de devolvidas) rodando dentro da API.
    tarefas_automaticas: bool = field(default_factory=lambda: _bool("TAREFAS_AUTOMATICAS", "true"))

    @property
    def azure_configurado(self) -> bool:
        return bool(self.azure_client_id and self.azure_client_secret and self.azure_tenant_id)

    def validar(self) -> None:
        """Falha cedo (no startup) em configuração perigosa ou incompleta."""
        if self.app_env not in AMBIENTES:
            raise RuntimeError(f"APP_ENV inválido: {self.app_env!r} (use local, hml ou main).")
        if not self.db_url:
            raise RuntimeError("DB_URL não configurado.")
        if self.dev_login_enabled and self.app_env != "local":
            raise RuntimeError("DEV_LOGIN_ENABLED só pode ser usado com APP_ENV=local.")


APP_VERSION = _ler("VERSION") or "0.0.0-dev"
APP_RELEASE_DATE = _ler("RELEASE_DATE")
APP_COMMIT_HASH = _ler("COMMIT_HASH")


def get_settings() -> Settings:
    return Settings()
