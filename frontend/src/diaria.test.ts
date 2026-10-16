import { describe, expect, it } from 'vitest'
import { linhasParaApi, quantidadeDiarias, subtotalLinha, totalDiaria, type LinhaDiariaForm } from '@/diaria'

const integral = (q: string): LinhaDiariaForm => ({ tipo: 'integral', quantidade: q, valor: '' })
const parcial = (q: string, v: string): LinhaDiariaForm => ({ tipo: 'parcial', quantidade: q, valor: v })

describe('Diária de Viagem', () => {
  it('soma integrais (valor fixo) e parciais (valor informado)', () => {
    expect(totalDiaria([integral('2'), parcial('1', '80,00')], 135)).toBe(350)
  })

  it('ignora linhas incompletas no total', () => {
    expect(subtotalLinha(parcial('1', ''), 135)).toBe(0)
    expect(subtotalLinha(integral(''), 135)).toBe(0)
    expect(subtotalLinha(integral('1,5'), 135)).toBe(0)
    expect(totalDiaria([integral('1'), parcial('2', 'abc')], 135)).toBe(135)
  })

  it('parcial não tem teto', () => {
    expect(subtotalLinha(parcial('1', '1.500,50'), 135)).toBe(1500.5)
  })

  it('conta as diárias das linhas', () => {
    expect(quantidadeDiarias([integral('2'), parcial('3', '10'), integral('x')])).toBe(5)
  })

  it('a integral não manda valor para a API', () => {
    expect(linhasParaApi([integral('2'), parcial('1', '80,00')])).toEqual([
      { tipo: 'integral', quantidade: 2 },
      { tipo: 'parcial', quantidade: 1, valor: '80,00' },
    ])
  })
})
