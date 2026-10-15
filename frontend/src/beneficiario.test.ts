import { describe, expect, it } from 'vitest'
import {
  BENEFICIARIO_VAZIO,
  beneficiarioEhGestor,
  camposBeneficiario,
  precisaDosDados,
} from '@/beneficiario'

const conhecido = { email: 'bia@tecnored.com.br', nome: 'Bia', perfil_completo: true, eh_gestor: false }

describe('pedido em nome de outra pessoa', () => {
  it('pedido para si mesmo não manda nada', () => {
    expect(camposBeneficiario(BENEFICIARIO_VAZIO)).toEqual({})
    expect(camposBeneficiario({ ...BENEFICIARIO_VAZIO, ativo: true })).toEqual({})
  })
  it('colega com perfil completo manda só o e-mail', () => {
    const b = { ...BENEFICIARIO_VAZIO, ativo: true, email: ' bia@tecnored.com.br ', conhecido }
    expect(precisaDosDados(b)).toBe(false)
    expect(camposBeneficiario(b)).toEqual({ beneficiario_email: 'bia@tecnored.com.br' })
  })
  it('quem nunca entrou manda nome e matrícula', () => {
    const b = {
      ...BENEFICIARIO_VAZIO,
      ativo: true,
      email: 'novo@tecnored.com.br',
      nome: 'Novo',
      matricula: '77',
    }
    expect(precisaDosDados(b)).toBe(true)
    expect(camposBeneficiario(b)).toEqual({
      beneficiario_email: 'novo@tecnored.com.br',
      beneficiario_nome: 'Novo',
      beneficiario_matricula: '77',
    })
  })
  it('descobre se a pessoa é gestora pela busca ou pela lista de gestores', () => {
    const b = { ...BENEFICIARIO_VAZIO, ativo: true, email: 'Chefe@Tecnored.com.br' }
    expect(beneficiarioEhGestor(b, [])).toBe(false)
    expect(beneficiarioEhGestor(b, [{ email: 'chefe@tecnored.com.br', nome: 'Chefe' }])).toBe(true)
    expect(beneficiarioEhGestor({ ...b, conhecido: { ...conhecido, eh_gestor: true } }, [])).toBe(
      true
    )
  })
})
