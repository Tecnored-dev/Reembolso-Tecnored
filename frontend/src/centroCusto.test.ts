import { describe, expect, it } from 'vitest'
import { centroCustoInicial } from '@/centroCusto'
import type { Perfil, Solicitacao } from '@/types'

const centros = [
  { id: 1, rotulo: '3350 - T.I / T.A' },
  { id: 2, rotulo: '4110 - CONTROLADORIA' },
]
const perfil = (id: number | null): Perfil => ({
  email: 'a@b',
  nome: 'A',
  matricula: '1',
  completo: true,
  centro_custo: id === null ? null : { id, rotulo: 'x' },
})

describe('centro de custo inicial', () => {
  it('pedido novo sugere o último usado', () => {
    expect(centroCustoInicial(centros, perfil(2), null)).toBe('2')
  })
  it('sem último usado (ou inativo) começa vazio', () => {
    expect(centroCustoInicial(centros, perfil(null), null)).toBe('')
    expect(centroCustoInicial(centros, perfil(9), null)).toBe('')
  })
  it('correção usa o centro de custo do pedido', () => {
    const original = { centro_custo: '3350 - T.I / T.A' } as Solicitacao
    expect(centroCustoInicial(centros, perfil(2), original)).toBe('1')
  })
})
