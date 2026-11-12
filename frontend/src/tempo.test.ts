import { describe, expect, it } from 'vitest'
import { diasDesde, emAndamento, textoParado } from './tempo'

describe('diasDesde', () => {
  const agora = new Date('2026-10-20T12:00:00Z')

  it('conta dias inteiros', () => {
    expect(diasDesde('2026-10-17T11:00:00Z', agora)).toBe(3)
    expect(diasDesde('2026-10-20T08:00:00Z', agora)).toBe(0)
  })

  it('nunca fica negativo nem quebra com data inválida', () => {
    expect(diasDesde('2026-10-25T12:00:00Z', agora)).toBe(0)
    expect(diasDesde('não é data', agora)).toBe(0)
  })
})

describe('textoParado', () => {
  it('fala em português', () => {
    expect(textoParado(0)).toBe('hoje')
    expect(textoParado(1)).toBe('há 1 dia')
    expect(textoParado(4)).toBe('há 4 dias')
  })
})

describe('emAndamento', () => {
  it('separa o que terminou do que está andando', () => {
    expect(emAndamento('em_conferencia')).toBe(true)
    expect(emAndamento('aguardando_prestacao')).toBe(true)
    expect(emAndamento('pago')).toBe(false)
    expect(emAndamento('recusado')).toBe(false)
    expect(emAndamento('encerrado')).toBe(false)
    expect(emAndamento('cancelado')).toBe(false)
  })
})

describe('diasDesde com data da API (UTC sem fuso)', () => {
  it('lê como UTC, não como horário local', () => {
    // 5 dias e 1 hora depois, em UTC: em qualquer fuso continua sendo 5 dias.
    const agora = new Date('2026-10-11T15:00:00Z')
    expect(diasDesde('2026-10-06T14:00:00', agora)).toBe(5)
    expect(diasDesde('2026-10-06T14:00:00.123456', agora)).toBe(5)
    expect(diasDesde('2026-10-06T14:00:00+00:00', agora)).toBe(5)
  })
})
