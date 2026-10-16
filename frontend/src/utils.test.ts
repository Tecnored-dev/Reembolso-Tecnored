import { describe, expect, it } from 'vitest'
import {
  alertasViagem,
  calcularDiarias,
  caminhoInterno,
  formatarData,
  formatarMoeda,
  formatVersion,
  lerValor,
  mensagemErro,
  rotuloPapel,
  somarValores,
} from '@/utils'
import type { AppConfig } from '@/types'

const base: AppConfig = {
  title: 'Reembolso',
  welcome_msg: '',
  bg_color: '#000',
  env: 'local',
  version: '1.2.0',
  released_at: '2026-10-01',
  commit_hash: 'abc1234',
  login_microsoft: false,
  login_dev: true,
}

describe('formatVersion', () => {
  it('monta versão, hash e data', () => {
    expect(formatVersion(base)).toBe('v1.2.0+abc1234 (2026-10-01)')
  })
  it('omite partes ausentes', () => {
    expect(formatVersion({ ...base, commit_hash: null, released_at: null })).toBe('v1.2.0')
    expect(formatVersion(null)).toBeNull()
  })
})

describe('rotuloPapel', () => {
  it('traduz os papéis', () => {
    expect(rotuloPapel('financeiro')).toBe('Financeiro')
  })
})

describe('formatação', () => {
  it('moeda em reais', () => {
    expect(formatarMoeda('1234.5').replace(/\s/g, ' ')).toBe('R$ 1.234,50')
  })
  it('data sem fuso', () => {
    expect(formatarData('2026-10-06')).toBe('06/10/2026')
    expect(formatarData(null)).toBe('—')
  })
})

describe('mensagemErro', () => {
  it('usa o detail da API quando é texto', () => {
    expect(mensagemErro({ response: { data: { detail: 'Gestor não encontrado' } } })).toBe(
      'Gestor não encontrado'
    )
  })
  it('erro de validação do FastAPI vira mensagem genérica', () => {
    expect(mensagemErro({ response: { data: { detail: [{ loc: ['x'] }] } } })).toBe(
      'Confira os campos preenchidos.'
    )
  })
})

describe('lerValor', () => {
  it('aceita vírgula, ponto e milhar', () => {
    expect(lerValor('45,90')).toBe(45.9)
    expect(lerValor('45.90')).toBe(45.9)
    expect(lerValor('1.234,56')).toBe(1234.56)
    expect(lerValor('R$ 10')).toBe(10)
    expect(lerValor('')).toBeNaN()
  })
})

describe('caminhoInterno', () => {
  it('aceita caminho do próprio site', () => {
    expect(caminhoInterno('/nova')).toBe('/nova')
    expect(caminhoInterno('/solicitacoes/3?x=1')).toBe('/solicitacoes/3?x=1')
  })
  it('recusa outro domínio e cai no padrão', () => {
    for (const ruim of [null, '', 'nova', 'https://mal.com', '//mal.com', '/\\mal.com', '/\\/mal.com', '\\\\mal.com']) {
      expect(caminhoInterno(ruim)).toBe('/inicio')
    }
  })
})

describe('alertasViagem', () => {
  const nota = (categoria: string, data: string, valor: string) => ({ categoria, data, valor })

  it('soma as refeições do mesmo dia', () => {
    const alertas = alertasViagem(
      [nota('refeicao', '2026-10-05', '80,00'), nota('refeicao', '2026-10-05', '70,00')],
      135,
      5000
    )
    expect(alertas).toHaveLength(1)
    expect(alertas[0]).toContain('05/10')
  })
  it('não alerta refeições em dias diferentes nem outras categorias', () => {
    const alertas = alertasViagem(
      [
        nota('refeicao', '2026-10-05', '80,00'),
        nota('refeicao', '2026-10-06', '70,00'),
        nota('hospedagem', '2026-10-05', '400,00'),
      ],
      135,
      5000
    )
    expect(alertas).toEqual([])
  })
  it('alerta o total acima do limite e ignora valor inválido', () => {
    const alertas = alertasViagem(
      [nota('hospedagem', '2026-10-05', '3.000,00'), nota('transporte', '2026-10-05', '2500'), nota('outros', '', 'abc')],
      135,
      5000
    )
    expect(alertas).toEqual([expect.stringContaining('Total acima')])
  })
})

describe('alertasViagem na alimentação (R$ 40 por dia, refeição + almoço em Pinda)', () => {
  const nota = (categoria: string, data: string, valor: string) => ({ categoria, data, valor })
  const refeicao = ['refeicao', 'almoco_pinda']
  it('soma refeição e almoço em Pinda do mesmo dia', () => {
    const alertas = alertasViagem(
      [nota('refeicao', '2026-10-05', '25,00'), nota('almoco_pinda', '2026-10-05', '20,00')],
      40,
      5000,
      refeicao
    )
    expect(alertas).toHaveLength(1)
    expect(alertas[0]).toMatch(/R\$\s40,00/)
  })
  it('Uber e hotel não contam como refeição', () => {
    expect(
      alertasViagem([nota('taxi_uber', '2026-10-05', '80,00')], 40, 5000, refeicao)
    ).toEqual([])
  })
})

describe('somarValores', () => {
  it('soma só os valores válidos', () => {
    expect(somarValores(['45,90', '1.000,10', '', 'x'])).toBeCloseTo(1046)
  })
})

describe('calcularDiarias', () => {
  it('conta o dia da ida e o da volta', () => {
    expect(calcularDiarias('2026-10-05', '2026-10-07')).toBe(3)
    expect(calcularDiarias('2026-10-05', '2026-10-05')).toBe(1)
  })
  it('atravessa mês e horário de verão sem errar', () => {
    expect(calcularDiarias('2026-09-30', '2026-10-01')).toBe(2)
    expect(calcularDiarias('2026-10-31', '2026-11-03')).toBe(4)
  })
  it('devolve 0 sem data ou com fim antes do início', () => {
    expect(calcularDiarias('', '2026-10-05')).toBe(0)
    expect(calcularDiarias('2026-10-07', '2026-10-05')).toBe(0)
  })
})
