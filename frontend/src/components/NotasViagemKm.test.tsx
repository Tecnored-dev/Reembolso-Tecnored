import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it } from 'vitest'
import NotasViagem from '@/components/NotasViagem'
import { novaNota, type NotaForm } from '@/notas'
import type { Cadastros } from '@/types'

const CADASTROS = {
  categorias_viagem: [
    { id: 'refeicao', rotulo: 'Refeição - Nacional' },
    { id: 'quilometragem', rotulo: 'Quilometragem com veículo próprio' },
  ],
  limite_refeicao_dia: '135.00',
  limite_solicitacao: '5000.00',
  valor_km: '1.00',
  km_maximo: '2000',
  max_pontos_percurso: 4,
} as unknown as Cadastros

function Tela({ semKm = false }) {
  const [notas, setNotas] = useState<NotaForm[]>([novaNota()])
  return <NotasViagem notas={notas} setNotas={setNotas} cadastros={CADASTROS} semKm={semKm} />
}

const escolherKm = () =>
  fireEvent.change(screen.getByLabelText(/Categoria/), { target: { value: 'quilometragem' } })

afterEach(cleanup)

describe('NotasViagem - quilometragem', () => {
  it('troca o comprovante e o valor por percurso e km, e calcula o valor', () => {
    render(<Tela />)
    expect(screen.getByLabelText(/Foto ou PDF da nota/)).toBeTruthy()
    escolherKm()
    expect(screen.queryByLabelText(/Foto ou PDF da nota/)).toBeNull()
    expect(screen.queryByLabelText(/Valor \(R\$\)/)).toBeNull()
    expect(screen.getByLabelText('Origem')).toBeTruthy()
    expect(screen.getByLabelText('Destino')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Km rodados'), { target: { value: '42,5' } })
    expect(screen.getByText(/Valor da nota/).textContent).toMatch(/42,50/)
  })

  it('adiciona e remove paradas entre a origem e o destino, até o limite', () => {
    render(<Tela />)
    escolherKm()
    fireEvent.click(screen.getByRole('button', { name: /Adicionar parada/ }))
    expect(screen.getByLabelText('Parada 1')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Adicionar parada/ }))
    expect((screen.getByRole('button', { name: /Adicionar parada/ }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getAllByRole('button', { name: 'Remover' })[0])
    expect(screen.queryByLabelText('Parada 2')).toBeNull()
    expect(screen.getByLabelText('Destino')).toBeTruthy()
  })

  it('na prestação do adiantamento a quilometragem não aparece', () => {
    render(<Tela semKm />)
    expect(screen.queryByRole('option', { name: /Quilometragem/ })).toBeNull()
    expect(screen.getByRole('option', { name: /Refeição/ })).toBeTruthy()
  })
})
