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
  // Só do adiantamento de viagem (depois do pagamento das diárias)
  | 'aguardando_prestacao'
  | 'prestacao_em_conferencia'
  | 'prestacao_devolvida'
  | 'aguardando_devolucao'
  | 'devolucao_em_conferencia'
  | 'diferenca_aguardando_gestor'
  | 'diferenca_aguardando_pagamento'
  | 'encerrado'

export type Acao =
  | 'conferir'
  | 'devolver'
  | 'aprovar'
  | 'pagar'
  | 'reenviar'
  | 'prestar_contas'
  | 'enviar_comprovante'
  | 'confirmar_devolucao'
  | 'recusar_comprovante'

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
  /** Adiantamento: valor de uma diária e máximo de diárias por pedido */
  valor_diaria: string
  max_diarias: number
}

export type TipoSolicitacao = 'alimentacao' | 'viagem' | 'adiantamento' | 'diversas'

/** Tipos com uma nota só, no formulário simples. */
export type TipoUmaNota = 'alimentacao' | 'diversas'

/** Chave do tipo de despesa de viagem (a lista vem de GET /api/cadastros). */
export type CategoriaViagem = string

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
  /** Só quando alguém pediu em nome do solicitante (quem recebe). */
  criado_por_nome: string | null
  criado_por_email: string | null
  gestor_nome: string | null
  descricao: string
  /** Só em viagem e adiantamento */
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
  /** Só no adiantamento: o valor adiantado é `valor_total` */
  diarias: number | null
  /** Diária complementar (quem recebe auxílio refeição): o valor foi informado */
  diaria_complementar: boolean
  /** Valor da diária complementar, já somado em `valor_total` */
  valor_complementar: string | null
  /** Data limite da prestação de contas (60 dias depois da volta) */
  prazo_prestacao: string | null
  valor_diaria: string | null
  /** Soma das notas da prestação de contas */
  valor_gasto: string | null
  /** Adiantado − gasto: positivo = sobra a devolver; negativo = diferença a receber */
  saldo: string | null
  prestacao_enviada_em: string | null
  prestacao_conferida_por: string | null
  devolucao_confirmada_por: string | null
  diferenca_aprovada_por: string | null
  data_pagamento_diferenca: string | null
  encerrado_em: string | null
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

/** GET /api/usuarios?busca= — colegas que já entraram no sistema */
export interface UsuarioBusca {
  email: string
  nome: string
  perfil_completo: boolean
  eh_gestor: boolean
}
