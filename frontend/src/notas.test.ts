import { describe, expect, it } from 'vitest'
import {
  aplicarLeitura,
  anexarNotas,
  conferirNotas,
  editarNota,
  limparLeitura,
  novaNota,
  valorDaQuilometragem,
  type NotaForm,
} from '@/notas'
import type { AnaliseComprovante, CampoLido } from '@/types'

const VAZIO: CampoLido = { valor: null, estado: 'nao_identificado', alternativas: [] }
const lido = (valor: string, estado: CampoLido['estado'] = 'identificado'): CampoLido => ({
  valor,
  estado,
  alternativas: [],
})

function analise(campos: Partial<AnaliseComprovante['campos']> = {}): AnaliseComprovante {
  return {
    status: 'lido',
    origem: 'ocr',
    campos: {
      data: lido('2026-10-18'),
      valor_total: lido('48.90'),
      estabelecimento: lido('RESTAURANTE SABOR DO VALE LTDA'),
      cnpj: lido('11222333000181'),
      numero_documento: lido('12345'),
      categoria_sugerida: lido('refeicao'),
      ...campos,
    },
    avisos: [],
  }
}

const OPCOES = { categorias: ['refeicao', 'hospedagem', 'taxi_uber'], hoje: '2026-10-20' }

describe('aplicarLeitura', () => {
  it('preenche a nota vazia e marca o que veio da leitura', () => {
    const nota = aplicarLeitura(novaNota(), analise(), OPCOES)
    expect(nota).toMatchObject({
      categoria: 'refeicao',
      data: '2026-10-18',
      valor: '48,90',
      descricao: 'RESTAURANTE SABOR DO VALE LTDA',
    })
    expect(nota.lidos).toEqual({
      categoria: 'identificado',
      data: 'identificado',
      valor: 'identificado',
      descricao: 'identificado',
    })
  })

  it('não sobrescreve o que o colaborador digitou', () => {
    const digitada: NotaForm = { ...novaNota(), valor: '50,00', descricao: 'Almoço com cliente' }
    const nota = aplicarLeitura(digitada, analise(), OPCOES)
    expect(nota.valor).toBe('50,00')
    expect(nota.descricao).toBe('Almoço com cliente')
    expect(nota.data).toBe('2026-10-18')
    expect(nota.lidos).not.toHaveProperty('valor')
    expect(nota.lidos).not.toHaveProperty('descricao')
  })

  it('campo ambíguo é preenchido, mas marcado para conferir', () => {
    const nota = aplicarLeitura(novaNota(), analise({ valor_total: lido('180.00', 'ambiguo') }), OPCOES)
    expect(nota.valor).toBe('180,00')
    expect(nota.lidos?.valor).toBe('ambiguo')
  })

  it('categoria só quando não há dúvida e quando existe na nota', () => {
    const empate = aplicarLeitura(novaNota(), analise({ categoria_sugerida: lido('refeicao', 'ambiguo') }), OPCOES)
    expect(empate.categoria).toBe('')
    const desconhecida = aplicarLeitura(novaNota(), analise({ categoria_sugerida: lido('lavanderia') }), OPCOES)
    expect(desconhecida.categoria).toBe('')
    // Despesas diversas: a nota não tem categoria.
    const diversas = aplicarLeitura(novaNota(), analise(), { ...OPCOES, categorias: [] })
    expect(diversas.categoria).toBe('')
    expect(diversas.lidos).not.toHaveProperty('categoria')
  })

  it('não preenche data no futuro', () => {
    const nota = aplicarLeitura(novaNota(), analise({ data: lido('2026-12-25', 'ambiguo') }), OPCOES)
    expect(nota.data).toBe('')
    expect(nota.lidos).not.toHaveProperty('data')
  })

  it('nome do estabelecimento só vai para a descrição quando é certo', () => {
    const palpite = aplicarLeitura(novaNota(), analise({ estabelecimento: lido('OBRIGADO', 'ambiguo') }), OPCOES)
    expect(palpite.descricao).toBe('')
    const longo = aplicarLeitura(novaNota(), analise({ estabelecimento: lido('X'.repeat(300)) }), OPCOES)
    expect(longo.descricao).toHaveLength(200)
  })

  it('leitura ilegível não muda a nota', () => {
    const ilegivel: AnaliseComprovante = {
      ...analise(),
      status: 'ilegivel',
      campos: {
        data: VAZIO,
        valor_total: VAZIO,
        estabelecimento: VAZIO,
        cnpj: VAZIO,
        numero_documento: VAZIO,
        categoria_sugerida: VAZIO,
      },
    }
    const digitada: NotaForm = { ...novaNota(), valor: '12,00' }
    const nota = aplicarLeitura(digitada, ilegivel, OPCOES)
    expect(nota).toMatchObject({ categoria: '', data: '', valor: '12,00', descricao: '' })
    expect(nota.lidos).toEqual({})
  })

  it('trocar o arquivo troca o que veio da leitura anterior', () => {
    const primeira = aplicarLeitura(novaNota(), analise(), OPCOES)
    const corrigida = editarNota(primeira, { valor: '49,90' })
    const segunda = aplicarLeitura(
      corrigida,
      analise({ valor_total: lido('10.00'), data: VAZIO, estabelecimento: lido('HOTEL CENTRAL'), categoria_sugerida: lido('hospedagem') }),
      OPCOES
    )
    expect(segunda).toMatchObject({
      categoria: 'hospedagem',
      data: '', // a data era do arquivo anterior e o novo não tem
      valor: '49,90', // corrigido pelo colaborador: fica
      descricao: 'HOTEL CENTRAL',
    })
    expect(segunda.lidos).toEqual({ categoria: 'identificado', descricao: 'identificado' })
  })

  it('não mexe no arquivo nem na nota original', () => {
    const arquivo = new File(['x'], 'nota.jpg', { type: 'image/jpeg' })
    const original: NotaForm = { ...novaNota(), arquivo }
    const nota = aplicarLeitura(original, analise(), OPCOES)
    expect(nota.arquivo).toBe(arquivo)
    expect(nota.chave).toBe(original.chave)
    expect(original.valor).toBe('')
  })
})

describe('editarNota', () => {
  it('correção manual tira a marca de "lido do comprovante"', () => {
    const nota = editarNota(aplicarLeitura(novaNota(), analise(), OPCOES), { data: '2026-10-17' })
    expect(nota.data).toBe('2026-10-17')
    expect(nota.lidos).not.toHaveProperty('data')
    expect(nota.lidos?.valor).toBe('identificado')
  })

  it('nota sem leitura muda como antes', () => {
    const nota = novaNota()
    expect(editarNota(nota, { valor: '1,00' })).toEqual({ ...nota, valor: '1,00' })
  })
})

describe('limparLeitura', () => {
  it('apaga só o que veio da leitura', () => {
    const lida = editarNota(aplicarLeitura(novaNota(), analise(), OPCOES), { valor: '49,90' })
    const nota = limparLeitura(lida)
    expect(nota).toMatchObject({ categoria: '', data: '', valor: '49,90', descricao: '' })
    expect(nota.lidos).toEqual({})
  })
})

describe('anexarNotas com leitura', () => {
  it('envia os mesmos campos de sempre (a marca de leitura não vai para a API)', () => {
    const arquivo = new File(['x'], 'nota.jpg', { type: 'image/jpeg' })
    const nota = aplicarLeitura({ ...novaNota(), arquivo }, analise(), OPCOES)
    const form = new FormData()
    anexarNotas(form, [nota])
    expect(JSON.parse(form.get('despesas') as string)).toEqual([
      {
        categoria: 'refeicao',
        data_despesa: '2026-10-18',
        valor: '48,90',
        descricao: 'RESTAURANTE SABOR DO VALE LTDA',
        arquivo: 0,
      },
    ])
    expect(form.getAll('arquivos')).toHaveLength(1)
  })
})

describe('quilometragem', () => {
  const km = (extra: Partial<NotaForm> = {}): NotaForm => ({
    ...novaNota(),
    categoria: 'quilometragem',
    data: '2026-10-20',
    descricao: 'Visita ao cliente',
    km: '42,5',
    percurso: ['Rua A, 10', 'Av. B, 200', 'Rua A, 10'],
    ...extra,
  })

  it('valor = km x valor por km, vazio enquanto o km não for válido', () => {
    expect(valorDaQuilometragem('42,5', 1)).toBe('42,50')
    expect(valorDaQuilometragem('10', 1.5)).toBe('15,00')
    expect(valorDaQuilometragem('', 1)).toBe('')
    expect(valorDaQuilometragem('0', 1)).toBe('')
    expect(valorDaQuilometragem('abc', 1)).toBe('')
  })

  it('não pede comprovante, mas exige km, percurso e descrição', () => {
    expect(conferirNotas([km()])).toBeNull()
    expect(conferirNotas([km({ km: '' })])).toMatch(/km rodados/)
    expect(conferirNotas([km({ percurso: ['Rua A', ''] })])).toMatch(/origem/)
    expect(conferirNotas([km({ descricao: ' ' })])).toMatch(/descreva/)
  })

  it('envia km e percurso, sem valor nem arquivo', () => {
    const form = new FormData()
    anexarNotas(form, [km({ percurso: [' Rua A ', 'Av. B'] })])
    expect(JSON.parse(form.get('despesas') as string)).toEqual([
      {
        categoria: 'quilometragem',
        data_despesa: '2026-10-20',
        descricao: 'Visita ao cliente',
        km: '42,5',
        percurso: ['Rua A', 'Av. B'],
      },
    ])
    expect(form.getAll('arquivos')).toHaveLength(0)
  })

  it('nota comum continua exigindo o arquivo', () => {
    const comum: NotaForm = { ...novaNota(), categoria: 'refeicao', valor: '10,00' }
    expect(conferirNotas([comum])).toMatch(/anexe/)
  })
})
