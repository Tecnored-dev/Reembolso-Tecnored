import { describe, expect, it } from 'vitest'
import {
  caminhoInterno,
  formatarData,
  formatarMoeda,
  formatVersion,
  lerValor,
  mensagemErro,
  rotuloPapel,
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
