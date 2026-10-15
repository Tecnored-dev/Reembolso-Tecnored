import type { Status } from '@/types'
import styles from './StatusBadge.module.css'

const CURTO: Record<Status, string> = {
  // Nomes do fluxo principal pedidos pela Thais (15/10).
  em_conferencia: 'Pendente de conferência',
  aguardando_gestor: 'Pendente de aprovação',
  aguardando_pagamento: 'Aguardando pagamento',
  pago: 'Finalizado - Pago',
  recusado: 'Finalizado - Recusado',
  devolvido: 'Devolvida',
  cancelado: 'Cancelada',
  aguardando_prestacao: 'Prestar contas',
  prestacao_em_conferencia: 'Prestação em conferência',
  prestacao_devolvida: 'Prestação devolvida',
  aguardando_devolucao: 'Devolver sobra',
  devolucao_em_conferencia: 'Devolução enviada',
  diferenca_aguardando_gestor: 'Diferença com o gestor',
  diferenca_aguardando_pagamento: 'Diferença a pagar',
  encerrado: 'Encerrada',
}

export default function StatusBadge({ status, titulo }: { status: Status; titulo?: string }) {
  return (
    <span className={`${styles.badge} ${styles[status]}`} title={titulo}>
      {CURTO[status] ?? status}
    </span>
  )
}
