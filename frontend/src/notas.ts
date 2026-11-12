// Notas de viagem no formulário (reembolso de viagem e prestação de contas do
// adiantamento): estado de cada nota e como ela vai para a API.
import type { AnaliseComprovante, CategoriaViagem, Despesa, EstadoCampoLido } from '@/types'
import { lerValor } from '@/utils'

/** Campos da nota que a leitura do comprovante pode preencher. */
export type CampoLidoNota = 'categoria' | 'data' | 'valor' | 'descricao'

/** Categoria da quilometragem: sem comprovante, valor = km x valor por km (Thais, 22/10). */
export const CATEGORIA_KM = 'quilometragem'

export interface NotaForm {
  chave: number
  /** Só na correção: nota que já foi enviada. */
  id?: number
  categoria: CategoriaViagem | ''
  data: string
  valor: string
  descricao: string
  arquivo: File | null
  /** Só na quilometragem: km rodados (digitados, versão provisória). */
  km: string
  /** Só na quilometragem: origem, paradas e destino, nessa ordem (mínimo 2). */
  percurso: string[]
  /** Nome da nota já enviada (correção), mostrado enquanto não for trocada. */
  arquivoAtual?: string
  /**
   * Campos preenchidos pela leitura do comprovante, para a tela pedir que o
   * colaborador confira. Só existe na tela: não vai para a API.
   */
  lidos?: Partial<Record<CampoLidoNota, EstadoCampoLido>>
}

let proximaChave = 1
export function novaNota(): NotaForm {
  return {
    chave: proximaChave++,
    categoria: '',
    data: '',
    valor: '',
    descricao: '',
    arquivo: null,
    km: '',
    percurso: ['', ''],
  }
}

/** Valor da quilometragem ("42,50") ou '' enquanto o km não for válido. */
export function valorDaQuilometragem(km: string, valorPorKm: number): string {
  const n = lerValor(km)
  if (Number.isNaN(n) || n <= 0) return ''
  return (Math.round(n * valorPorKm * 100) / 100).toFixed(2).replace('.', ',')
}

/** Notas já enviadas, para corrigir em cima (o comprovante da devolução fica de fora). */
export function notasEnviadas(despesas: Despesa[]): NotaForm[] {
  return despesas
    .filter((d) => d.categoria !== 'comprovante_devolucao')
    .map((d) => ({
      chave: proximaChave++,
      id: d.id,
      categoria: d.categoria as CategoriaViagem,
      data: d.data_despesa,
      valor: Number(d.valor).toFixed(2).replace('.', ','),
      descricao: d.descricao ?? '',
      arquivo: null,
      km: d.km ? d.km.replace('.', ',') : '',
      percurso: d.percurso && d.percurso.length >= 2 ? d.percurso : ['', ''],
      arquivoAtual: d.arquivo_nome ?? undefined,
    }))
}

/** Erro que dá para apontar antes de enviar, ou null. */
export function conferirNotas(notas: NotaForm[]): string | null {
  if (notas.length === 0) return 'Inclua pelo menos uma nota.'
  for (const [i, n] of notas.entries()) {
    if (n.categoria === CATEGORIA_KM) {
      const km = lerValor(n.km)
      if (Number.isNaN(km) || km <= 0) return `Nota ${i + 1}: informe os km rodados.`
      if (n.percurso.length < 2 || n.percurso.some((p) => !p.trim()))
        return `Nota ${i + 1}: informe a origem, o destino e as paradas (preencha ou remova as vazias).`
      if (!n.descricao.trim()) return `Nota ${i + 1}: descreva a quilometragem.`
    } else if (!n.arquivo && !n.id) {
      return `Nota ${i + 1}: anexe a foto ou o PDF.`
    } else if (!n.arquivo && !n.arquivoAtual) {
      return `Nota ${i + 1}: anexe a foto ou o PDF.` // era quilometragem e mudou de tipo
    }
  }
  return null
}

/**
 * Coloca as notas no formulário: os arquivos vão numa lista (`arquivos`) e
 * cada nota diz a posição do seu arquivo nela (campo `despesas`, em JSON).
 */
export function anexarNotas(form: FormData, notas: NotaForm[]): void {
  const despesas = notas.map((n) => {
    if (n.categoria === CATEGORIA_KM) {
      // Sem comprovante; o valor é calculado pela API (km x valor por km).
      return {
        ...(n.id ? { id: n.id } : {}),
        categoria: n.categoria,
        data_despesa: n.data,
        descricao: n.descricao,
        km: n.km,
        percurso: n.percurso.map((p) => p.trim()),
      }
    }
    let arquivo: number | undefined
    if (n.arquivo) {
      arquivo = form.getAll('arquivos').length
      form.append('arquivos', n.arquivo)
    }
    return {
      ...(n.id ? { id: n.id } : {}),
      categoria: n.categoria,
      data_despesa: n.data,
      valor: n.valor,
      descricao: n.descricao,
      ...(arquivo !== undefined ? { arquivo } : {}),
    }
  })
  form.append('despesas', JSON.stringify(despesas))
}

// ---------------------------------------------------------------------------
// Leitura automática do comprovante: só sugere, o colaborador confere.
// ---------------------------------------------------------------------------
const CAMPOS_LIDOS: CampoLidoNota[] = ['categoria', 'data', 'valor', 'descricao']

interface OpcoesLeitura {
  /** Categorias aceitas na nota (ids de `categorias_viagem`); vazio = nota sem categoria. */
  categorias: string[]
  /** Hoje (AAAA-MM-DD): data no futuro não é preenchida, a API recusaria. */
  hoje: string
}

/**
 * Coloca na nota o que a leitura do comprovante achou. Só preenche campo vazio
 * ou que veio de uma leitura anterior (o arquivo foi trocado): o que o
 * colaborador digitou nunca é sobrescrito. A categoria só entra quando a
 * leitura não tem dúvida; a descrição recebe o nome do estabelecimento.
 */
export function aplicarLeitura(
  nota: NotaForm,
  analise: AnaliseComprovante,
  opcoes: OpcoesLeitura
): NotaForm {
  const { data, valor_total, categoria_sugerida, estabelecimento } = analise.campos
  const sugestoes: Partial<Record<CampoLidoNota, { valor: string; estado: EstadoCampoLido }>> = {}
  function sugerir(campo: CampoLidoNota, valor: string | null | undefined, estado: EstadoCampoLido) {
    if (valor && estado !== 'nao_identificado') sugestoes[campo] = { valor, estado }
  }

  if (data.valor && data.valor <= opcoes.hoje) sugerir('data', data.valor, data.estado)
  sugerir('valor', valor_total.valor?.replace('.', ','), valor_total.estado)
  if (categoria_sugerida.estado === 'identificado' && opcoes.categorias.includes(categoria_sugerida.valor ?? ''))
    sugerir('categoria', categoria_sugerida.valor, 'identificado')
  if (estabelecimento.estado === 'identificado')
    sugerir('descricao', estabelecimento.valor?.slice(0, 200), 'identificado')

  const atualizada: NotaForm = { ...nota }
  const lidos: NotaForm['lidos'] = {}
  for (const campo of CAMPOS_LIDOS) {
    const daLeituraAnterior = nota.lidos?.[campo] !== undefined
    if (nota[campo] !== '' && !daLeituraAnterior) continue // digitado pelo colaborador
    const sugestao = sugestoes[campo]
    if (sugestao) {
      atualizada[campo] = sugestao.valor
      lidos[campo] = sugestao.estado
    } else if (daLeituraAnterior) {
      atualizada[campo] = '' // era do arquivo anterior
    }
  }
  return { ...atualizada, lidos }
}

/** Mudança feita pelo colaborador: o campo deixa de ser "lido do comprovante". */
export function editarNota(nota: NotaForm, mudanca: Partial<NotaForm>): NotaForm {
  if (!nota.lidos) return { ...nota, ...mudanca }
  const lidos = Object.fromEntries(Object.entries(nota.lidos).filter(([campo]) => !(campo in mudanca)))
  return { ...nota, ...mudanca, lidos }
}

/** Arquivo removido: apaga o que tinha vindo da leitura dele. */
export function limparLeitura(nota: NotaForm): NotaForm {
  const limpa: NotaForm = { ...nota, lidos: {} }
  for (const campo of CAMPOS_LIDOS) if (nota.lidos?.[campo] !== undefined) limpa[campo] = ''
  return limpa
}
