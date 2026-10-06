import { describe, expect, it } from 'vitest'
import { formatVersion, rotuloPapel } from '@/utils'
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
