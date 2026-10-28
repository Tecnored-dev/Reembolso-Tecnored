import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import NotasViagem from '@/components/NotasViagem'
import { novaNota, type NotaForm } from '@/notas'
import { analisarComprovante } from '@/services/comprovantes'
import type { AnaliseComprovante, Cadastros, CampoLido } from '@/types'

vi.mock('@/services/comprovantes', () => ({ analisarComprovante: vi.fn() }))
const analisar = vi.mocked(analisarComprovante)

const CADASTROS = {
  categorias_viagem: [
    { id: 'refeicao', rotulo: 'Refeição - Nacional' },
    { id: 'hospedagem', rotulo: 'Hospedagem' },
  ],
  limite_refeicao_dia: '135.00',
  limite_solicitacao: '5000.00',
} as unknown as Cadastros

const VAZIO: CampoLido = { valor: null, estado: 'nao_identificado', alternativas: [] }
const lido = (valor: string, estado: CampoLido['estado'] = 'identificado', alternativas: string[] = []) => ({
  valor,
  estado,
  alternativas,
})

function analise(campos: Partial<AnaliseComprovante['campos']> = {}, extra: Partial<AnaliseComprovante> = {}) {
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
    ...extra,
  } as AnaliseComprovante
}

function Tela({ semCategoria = false, lerComprovante = true }) {
  const [notas, setNotas] = useState<NotaForm[]>([novaNota()])
  return (
    <NotasViagem
      notas={notas}
      setNotas={setNotas}
      cadastros={CADASTROS}
      semCategoria={semCategoria}
      lerComprovante={lerComprovante}
    />
  )
}

const foto = () => new File(['foto'], 'nota.jpg', { type: 'image/jpeg' })
const campo = (rotulo: RegExp) => screen.getByLabelText(rotulo) as HTMLInputElement
const anexar = (arquivo: File | null) =>
  fireEvent.change(screen.getByLabelText(/Foto ou PDF da nota/), { target: { files: arquivo ? [arquivo] : [] } })

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-20T12:00:00'))
  URL.createObjectURL = vi.fn(() => 'blob:previa')
  URL.revokeObjectURL = vi.fn()
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  analisar.mockReset()
})

describe('NotasViagem com leitura do comprovante', () => {
  it('lê a nota ao anexar e preenche os campos, marcados para conferir', async () => {
    analisar.mockResolvedValue(analise())
    render(<Tela />)
    const arquivo = foto()
    anexar(arquivo)

    expect(screen.getByText('Lendo a nota…')).toBeTruthy()
    expect(await screen.findByText(/Preenchemos os campos marcados/)).toBeTruthy()
    expect(analisar).toHaveBeenCalledWith(arquivo, expect.any(AbortSignal))

    expect(campo(/Valor \(R\$\)/).value).toBe('48,90')
    expect(campo(/^Data/).value).toBe('2026-10-18')
    expect((screen.getByLabelText(/Categoria/) as HTMLSelectElement).value).toBe('refeicao')
    expect(campo(/Descrição/).value).toBe('RESTAURANTE SABOR DO VALE LTDA')
    expect(screen.getAllByText('Lido da nota')).toHaveLength(4)
    expect(screen.getByText('CNPJ 11.222.333/0001-81 · nota nº 12345')).toBeTruthy()
  })

  it('correção manual tira o selo do campo e fica valendo', async () => {
    analisar.mockResolvedValue(analise())
    render(<Tela />)
    anexar(foto())
    await screen.findByText(/Preenchemos os campos marcados/)

    fireEvent.change(campo(/Valor \(R\$\)/), { target: { value: '50,00' } })
    expect(campo(/Valor \(R\$\)/).value).toBe('50,00')
    expect(screen.getByLabelText('Valor (R$)')).toBeTruthy() // rótulo sem selo
    expect(screen.getAllByText('Lido da nota')).toHaveLength(3)
  })

  it('não sobrescreve o que o colaborador já digitou', async () => {
    analisar.mockResolvedValue(analise())
    render(<Tela />)
    fireEvent.change(campo(/Valor \(R\$\)/), { target: { value: '52,00' } })
    anexar(foto())
    await screen.findByText(/Preenchemos os campos marcados/)
    expect(campo(/Valor \(R\$\)/).value).toBe('52,00')
  })

  it('campo ambíguo pede conferência e mostra o que mais foi lido', async () => {
    analisar.mockResolvedValue(
      analise(
        { valor_total: lido('180.00', 'ambiguo', ['150.00']) },
        { avisos: ['Não achamos o total na nota. Confira o valor.'] }
      )
    )
    render(<Tela />)
    anexar(foto())
    await screen.findByText(/Preenchemos os campos marcados/)
    expect(campo(/Valor \(R\$\)/).value).toBe('180,00')
    expect(screen.getByText('Confira')).toBeTruthy()
    expect(screen.getByText(/Também lemos: R\$\s150,00\./)).toBeTruthy()
    expect(screen.getByText('Não achamos o total na nota. Confira o valor.')).toBeTruthy()
  })

  it('falha na leitura avisa e deixa preencher à mão', async () => {
    analisar.mockRejectedValue({
      response: { status: 503, data: { detail: 'A leitura automática não está disponível agora. Preencha os dados à mão.' } },
    })
    render(<Tela />)
    anexar(foto())
    expect(await screen.findByText(/não está disponível agora/)).toBeTruthy()
    expect(campo(/Valor \(R\$\)/).value).toBe('')
    fireEvent.change(campo(/Valor \(R\$\)/), { target: { value: '30,00' } })
    expect(campo(/Valor \(R\$\)/).value).toBe('30,00')
  })

  it('sem resposta da API, mensagem genérica', async () => {
    analisar.mockRejectedValue(new Error('timeout of 30000ms exceeded'))
    render(<Tela />)
    anexar(foto())
    expect(
      await screen.findByText('A leitura automática não funcionou agora. Preencha os dados à mão.')
    ).toBeTruthy()
  })

  it('nota ilegível', async () => {
    const vazio = { data: VAZIO, valor_total: VAZIO, estabelecimento: VAZIO, cnpj: VAZIO }
    analisar.mockResolvedValue(
      analise({ ...vazio, numero_documento: VAZIO, categoria_sugerida: VAZIO }, { status: 'ilegivel' })
    )
    render(<Tela />)
    anexar(foto())
    expect(await screen.findByText('Não conseguimos ler esta nota. Preencha os dados à mão.')).toBeTruthy()
    expect(screen.queryByText('Lido da nota')).toBeNull()
  })

  it('despesas diversas: sem categoria, o resto é preenchido', async () => {
    analisar.mockResolvedValue(analise())
    render(<Tela semCategoria />)
    anexar(foto())
    await screen.findByText(/Preenchemos os campos marcados/)
    expect(screen.queryByLabelText(/Categoria/)).toBeNull()
    expect(campo(/Valor \(R\$\)/).value).toBe('48,90')
  })

  it('trocar o arquivo cancela a leitura anterior', async () => {
    analisar.mockReturnValueOnce(new Promise(() => {})).mockResolvedValueOnce(analise())
    render(<Tela />)
    anexar(foto())
    anexar(foto())
    await screen.findByText(/Preenchemos os campos marcados/)
    const [primeira, segunda] = analisar.mock.calls.map(([, sinal]) => sinal as AbortSignal)
    expect(primeira.aborted).toBe(true)
    expect(segunda.aborted).toBe(false)
  })

  it('tirar o arquivo apaga o que veio da leitura dele', async () => {
    analisar.mockResolvedValue(analise())
    render(<Tela />)
    anexar(foto())
    await screen.findByText(/Preenchemos os campos marcados/)
    fireEvent.change(campo(/^Data/), { target: { value: '2026-10-17' } })
    await act(async () => anexar(null))
    expect(campo(/Valor \(R\$\)/).value).toBe('')
    expect(campo(/^Data/).value).toBe('2026-10-17') // corrigida à mão: fica
    expect(screen.queryByText(/Preenchemos/)).toBeNull()
  })

  it('sem a leitura ligada, anexar não chama a API', () => {
    render(<Tela lerComprovante={false} />)
    anexar(foto())
    expect(analisar).not.toHaveBeenCalled()
    expect(screen.queryByText('Lendo a nota…')).toBeNull()
    expect(screen.queryByText(/Ao anexar, lemos a nota/)).toBeNull()
  })
})
