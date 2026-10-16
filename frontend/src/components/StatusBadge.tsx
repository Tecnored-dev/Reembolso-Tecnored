import Icone, { type NomeIcone } from '@/components/Icone'
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

// A cor diz com quem está o pedido agora; o ícone garante que não dependa só da cor.
type Familia = 'voce' | 'financeiro' | 'gestor' | 'concluido' | 'cancelado' | 'recusado'

const VISUAL: Record<Status, { familia: Familia; icone: NomeIcone }> = {
  em_conferencia: { familia: 'financeiro', icone: 'lupa' },
  aguardando_gestor: { familia: 'gestor', icone: 'pessoa' },
  aguardando_pagamento: { familia: 'financeiro', icone: 'cifrao' },
  pago: { familia: 'concluido', icone: 'check' },
  recusado: { familia: 'recusado', icone: 'x' },
  devolvido: { familia: 'voce', icone: 'seta-volta' },
  cancelado: { familia: 'cancelado', icone: 'x' },
  aguardando_prestacao: { familia: 'voce', icone: 'recibo' },
  prestacao_em_conferencia: { familia: 'financeiro', icone: 'lupa' },
  prestacao_devolvida: { familia: 'voce', icone: 'seta-volta' },
  aguardando_devolucao: { familia: 'voce', icone: 'carteira' },
  devolucao_em_conferencia: { familia: 'financeiro', icone: 'lupa' },
  diferenca_aguardando_gestor: { familia: 'gestor', icone: 'pessoa' },
  diferenca_aguardando_pagamento: { familia: 'financeiro', icone: 'cifrao' },
  encerrado: { familia: 'concluido', icone: 'check' },
}

export default function StatusBadge({ status, titulo }: { status: Status; titulo?: string }) {
  const visual = VISUAL[status] ?? { familia: 'cancelado', icone: 'info' }
  return (
    <span className={`${styles.badge} ${styles[visual.familia]}`} title={titulo}>
      <Icone nome={visual.icone} tamanho={15} />
      {CURTO[status] ?? status}
    </span>
  )
}
