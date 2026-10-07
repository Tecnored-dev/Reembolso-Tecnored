import type { Status } from '@/types'
import styles from './StatusBadge.module.css'

const CURTO: Record<Status, string> = {
  em_conferencia: 'Em conferência',
  aguardando_gestor: 'Com o gestor',
  aguardando_pagamento: 'Aguardando pagamento',
  pago: 'Paga',
  devolvido: 'Devolvida',
  cancelado: 'Cancelada',
}

export default function StatusBadge({ status, titulo }: { status: Status; titulo?: string }) {
  return (
    <span className={`${styles.badge} ${styles[status]}`} title={titulo}>
      {CURTO[status] ?? status}
    </span>
  )
}
