import { lerValor } from '@/utils'

// Linhas da Diária de Viagem (Thais, 15/10): "Valor Integral" usa o valor fixo
// da política; "Valor Parcial" usa o valor que o colaborador informa.
export type TipoLinhaDiaria = 'integral' | 'parcial'

export interface LinhaDiariaForm {
  tipo: TipoLinhaDiaria
  quantidade: string
  valor: string
}

export const novaLinhaDiaria = (): LinhaDiariaForm => ({ tipo: 'integral', quantidade: '1', valor: '' })

/** Valor de uma diária da linha (NaN enquanto a parcial não tem valor válido). */
function valorUnitario(linha: LinhaDiariaForm, valorDiaria: number): number {
  return linha.tipo === 'integral' ? valorDiaria : lerValor(linha.valor)
}

/** Subtotal da linha; 0 enquanto a quantidade ou o valor estiverem incompletos. */
export function subtotalLinha(linha: LinhaDiariaForm, valorDiaria: number): number {
  const quantidade = Number(linha.quantidade)
  const unitario = valorUnitario(linha, valorDiaria)
  if (!Number.isInteger(quantidade) || quantidade < 1 || Number.isNaN(unitario)) return 0
  return quantidade * unitario
}

export function totalDiaria(linhas: LinhaDiariaForm[], valorDiaria: number): number {
  return linhas.reduce((soma, linha) => soma + subtotalLinha(linha, valorDiaria), 0)
}

/** Total de diárias (quantidade) das linhas, para comparar com os dias da viagem. */
export function quantidadeDiarias(linhas: LinhaDiariaForm[]): number {
  return linhas.reduce((soma, linha) => {
    const n = Number(linha.quantidade)
    return soma + (Number.isInteger(n) && n > 0 ? n : 0)
  }, 0)
}

/** Corpo das linhas para a API (a integral não manda valor). */
export function linhasParaApi(linhas: LinhaDiariaForm[]) {
  return linhas.map((l) => ({
    tipo: l.tipo,
    quantidade: Number(l.quantidade) || 0,
    ...(l.tipo === 'parcial' ? { valor: l.valor } : {}),
  }))
}
