// Notas de viagem no formulário (reembolso de viagem e prestação de contas do
// adiantamento): estado de cada nota e como ela vai para a API.
import type { CategoriaViagem, Despesa } from '@/types'

export interface NotaForm {
  chave: number
  /** Só na correção: nota que já foi enviada. */
  id?: number
  categoria: CategoriaViagem | ''
  data: string
  valor: string
  descricao: string
  arquivo: File | null
  /** Nome da nota já enviada (correção), mostrado enquanto não for trocada. */
  arquivoAtual?: string
}

let proximaChave = 1
export function novaNota(): NotaForm {
  return { chave: proximaChave++, categoria: '', data: '', valor: '', descricao: '', arquivo: null }
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
      arquivoAtual: d.arquivo_nome,
    }))
}

/** Erro que dá para apontar antes de enviar, ou null. */
export function conferirNotas(notas: NotaForm[]): string | null {
  if (notas.length === 0) return 'Inclua pelo menos uma nota.'
  const semArquivo = notas.findIndex((n) => !n.arquivo && !n.id)
  if (semArquivo >= 0) return `Nota ${semArquivo + 1}: anexe a foto ou o PDF.`
  return null
}

/**
 * Coloca as notas no formulário: os arquivos vão numa lista (`arquivos`) e
 * cada nota diz a posição do seu arquivo nela (campo `despesas`, em JSON).
 */
export function anexarNotas(form: FormData, notas: NotaForm[]): void {
  const despesas = notas.map((n) => {
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
