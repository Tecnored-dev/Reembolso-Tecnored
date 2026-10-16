import ui from '@/styles/ui.module.css'
import type { Opcao } from '@/types'

interface Props {
  centros: Opcao[]
  valor: string
  onChange: (valor: string) => void
}

// Centro de custo do pedido (Thais, 15/10): saiu do perfil e é escolhido em
// cada pedido. Vem com o último usado, mas dá para trocar.
export default function CentroCustoCampo({ centros, valor, onChange }: Props) {
  return (
    <div className={ui.campo}>
      <label htmlFor="centroCusto">Centro de custo</label>
      <select id="centroCusto" value={valor} onChange={(e) => onChange(e.target.value)} required>
        <option value="">Selecione…</option>
        {centros.map((c) => (
          <option key={c.id} value={c.id}>
            {c.rotulo}
          </option>
        ))}
      </select>
      <span className={ui.ajuda}>Já vem com o último que você usou. Troque se precisar.</span>
    </div>
  )
}
