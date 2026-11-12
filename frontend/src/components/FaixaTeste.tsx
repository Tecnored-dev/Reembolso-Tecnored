import { useState } from 'react'
import { api } from '@/services/api'
import type { TesteEstado } from '@/types'
import { rotuloPapel } from '@/utils'
import styles from './FaixaTeste.module.css'

// Faixa fixa do painel de teste: avisa quem está sendo "visto como" e dá o
// caminho de volta para a conta real. Só aparece durante o "Ver como".
export default function FaixaTeste({ estado }: { estado: TesteEstado }) {
  const [saindo, setSaindo] = useState(false)
  if (!estado.vendo_como) return null
  const { nome, papeis } = estado.vendo_como

  async function voltar() {
    setSaindo(true)
    try {
      await api.post('/api/teste/voltar')
    } finally {
      window.location.assign('/teste')
    }
  }

  return (
    <div className={styles.faixa} role="status">
      <span>
        Você está vendo como <strong>{nome}</strong> ({papeis.map(rotuloPapel).join(' + ')}) —
        ambiente de teste
      </span>
      <button type="button" className={styles.voltar} onClick={voltar} disabled={saindo}>
        {saindo ? 'Voltando…' : 'Voltar para a minha conta'}
      </button>
    </div>
  )
}
