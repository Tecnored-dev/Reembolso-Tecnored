// ===========================================================================
// Tipos globais — espelham os contratos do backend FastAPI
// ===========================================================================

export type Papel = 'colaborador' | 'gestor' | 'financeiro' | 'admin'

/** Usuário autenticado — GET /api/session */
export interface Session {
  name: string
  email: string
  /** Sempre inclui "colaborador"; os demais vêm dos grupos do Azure AD */
  papeis: Papel[]
  /** "microsoft" (login direto), "cloudflare" (SSO externo) ou "dev" (só local) */
  login_method: 'microsoft' | 'cloudflare' | 'dev'
}

/** Configuração pública — GET /api/config */
export interface AppConfig {
  title: string
  welcome_msg: string
  bg_color: string
  env: string
  version: string
  released_at: string | null
  commit_hash: string | null
  login_microsoft: boolean
  login_dev: boolean
}

export interface ApiError {
  detail: string
}
