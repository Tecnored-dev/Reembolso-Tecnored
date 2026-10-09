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

// ===========================================================================
// Reembolso
// ===========================================================================
export type Status =
  | 'em_conferencia'
  | 'aguardando_gestor'
  | 'aguardando_pagamento'
  | 'pago'
  | 'devolvido'
  | 'cancelado'

export type Acao = 'conferir' | 'devolver' | 'aprovar' | 'pagar' | 'reenviar'

export interface Opcao {
  id: number
  rotulo: string
}

/** GET /api/perfil */
export interface Perfil {
  email: string
  nome: string
  matricula: string | null
  centro_custo: Opcao | null
  completo: boolean
}

/** GET /api/cadastros */
export interface Cadastros {
  centros_custo: Opcao[]
  empresas: { id: number; nome: string }[]
  limite_refeicao_dia: string
  limite_solicitacao: string
  categorias_viagem: { id: CategoriaViagem; rotulo: string }[]
}

export type TipoSolicitacao = 'alimentacao' | 'viagem'

export type CategoriaViagem = 'refeicao' | 'hospedagem' | 'transporte' | 'lavanderia' | 'outros'

export interface Gestor {
  email: string
  nome: string
}

/** Item das listas — GET /api/solicitacoes */
export interface SolicitacaoResumo {
  id: number
  codigo: string
  tipo: TipoSolicitacao
  tipo_rotulo: string
  status: Status
  status_rotulo: string
  solicitante_nome: string
  solicitante_email: string
  gestor_nome: string | null
  descricao: string
  /** Só em viagem */
  destino: string | null
  valor_total: string
  moeda: string
  alerta_limite: string | null
  enviado_em: string
  ultima_movimentacao_em: string
}

export interface Despesa {
  id: number
  categoria: string
  categoria_rotulo: string
  data_despesa: string
  valor: string
  descricao: string | null
  arquivo_nome: string
  arquivo_tipo: string
}

export interface EventoHistorico {
  acao: string
  status_para: Status
  status_rotulo: string
  usuario_nome: string
  comentario: string | null
  criado_em: string
}

/** GET /api/solicitacoes/:id */
export interface Solicitacao extends SolicitacaoResumo {
  matricula: string
  centro_custo: string
  empresa: string
  gestor_email: string | null
  pula_gestor: boolean
  viagem_inicio: string | null
  viagem_fim: string | null
  conferido_por: string | null
  conferido_em: string | null
  aprovado_por: string | null
  aprovado_em: string | null
  pago_por: string | null
  data_pagamento: string | null
  motivo_devolucao: string | null
  devolvido_por: string | null
  motivo_cancelamento: string | null
  despesas: Despesa[]
  historico: EventoHistorico[]
  acoes: Acao[]
}
