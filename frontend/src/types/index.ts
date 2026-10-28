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
  /** Leitura automática do comprovante disponível neste ambiente (OCR instalado) */
  leitura_comprovante: boolean
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
  // Recusa do gestor: final (Thais, 15/10)
  | 'recusado'
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
  | 'recusar'
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
  /** Último centro de custo usado num pedido: sugestão para o próximo */
  centro_custo: Opcao | null
  /** Só a matrícula é obrigatória (Thais, 15/10) */
  completo: boolean
}

/** GET /api/cadastros */
export interface Cadastros {
  centros_custo: Opcao[]
  empresas: { id: number; nome: string }[]
  limite_refeicao_dia: string
  limite_solicitacao: string
  categorias_viagem: { id: CategoriaViagem; rotulo: string }[]
  /** Reembolso de despesas: categorias de cada tipo (alimentação x diversas) */
  categorias_alimentacao: { id: CategoriaViagem; rotulo: string }[]
  categorias_diversas: { id: CategoriaViagem; rotulo: string }[]
  /** Motivos da despesa (lista do ARGO) — alimentação e despesas diversas */
  motivos: string[]
  /** Reembolso de despesas - alimentação: limite de refeição por dia (só alerta) */
  limite_alimentacao_dia: string
  /** Diária de viagem: valor da diária integral e máximo de diárias por linha */
  valor_diaria: string
  max_diarias: number
  /** Quilometragem (Thais, 22/10): valor por km, limite de km por nota e de pontos do percurso */
  valor_km: string
  km_maximo: string
  max_pontos_percurso: number
}

export interface LinhaDiaria {
  id: number
  tipo: 'integral' | 'parcial'
  tipo_rotulo: string
  quantidade: number
  valor_unitario: string
  subtotal: string
}

export type TipoSolicitacao = 'alimentacao' | 'viagem' | 'adiantamento' | 'diversas'

/** "Reembolso de despesas - Prestação de Contas": alimentação ou despesas diversas. */
export type TipoDespesas = 'alimentacao' | 'diversas'

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
  /** Vazio na quilometragem (não tem comprovante) */
  arquivo_nome: string | null
  arquivo_tipo: string | null
  /** Só na quilometragem: km informados e percurso (origem, paradas, destino) */
  km: string | null
  percurso: string[] | null
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
  /** Escolhido no pedido; o adiantamento não tem (nulo) */
  centro_custo: string | null
  empresa: string
  gestor_email: string | null
  pula_gestor: boolean
  /** Alimentação e despesas diversas (nulo em pedidos antigos) */
  motivo: string | null
  /** Pedidos antigos (antes de 15/10): pinda, maraba ou outro */
  local_refeicao: string | null
  local_refeicao_rotulo: string | null
  viagem_inicio: string | null
  viagem_fim: string | null
  /** Diária de viagem: "Viagem internacional?" (nulo nos pedidos antigos) */
  viagem_internacional: boolean | null
  /** Diária de viagem: linhas de valor integral/parcial (vazio nos pedidos antigos) */
  linhas_diaria: LinhaDiaria[]
  /** Adiantamento antigo (antes de 15/10): diárias contadas pelo sistema. O valor adiantado é `valor_total` */
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
  /** Recusa do gestor (final) */
  recusado_por: string | null
  recusado_em: string | null
  motivo_recusa: string | null
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

/** Painel de teste ("Ver como") — GET /api/teste/estado. Só existe em local/hml. */
export interface UsuarioTeste {
  chave: string
  email: string
  nome: string
  papeis: Papel[]
  descricao: string
}

export interface TesteEstado {
  ativo: boolean
  admin: boolean
  vendo_como: { email: string; nome: string; papeis: Papel[] } | null
  usuarios: UsuarioTeste[]
}

// ===========================================================================
// Leitura automática do comprovante — POST /api/comprovantes/analisar
// Só sugere: o colaborador confere e corrige antes de enviar.
// ===========================================================================
export type EstadoCampoLido = 'identificado' | 'ambiguo' | 'nao_identificado'

export interface CampoLido {
  valor: string | null
  estado: EstadoCampoLido
  /** Outros candidatos, quando o campo é ambíguo */
  alternativas: string[]
}

export interface AnaliseComprovante {
  status: 'lido' | 'parcial' | 'ilegivel'
  origem: 'texto_pdf' | 'ocr' | null
  campos: {
    /** AAAA-MM-DD */
    data: CampoLido
    /** "48.90" */
    valor_total: CampoLido
    estabelecimento: CampoLido
    /** 14 caracteres, sem pontuação */
    cnpj: CampoLido
    numero_documento: CampoLido
    /** Id de `categorias_viagem` (GET /api/cadastros) */
    categoria_sugerida: CampoLido
  }
  avisos: string[]
}
