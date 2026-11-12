import Icone from '@/components/Icone'
import { CURTO, VISUAL } from '@/statusVisual'
import type { Status } from '@/types'
import styles from './StatusBadge.module.css'

export default function StatusBadge({ status, titulo }: { status: Status; titulo?: string }) {
  const visual = VISUAL[status] ?? { familia: 'cancelado', icone: 'info' }
  return (
    <span className={`${styles.badge} ${styles[visual.familia]}`} title={titulo}>
      <Icone nome={visual.icone} tamanho={15} />
      {CURTO[status] ?? status}
    </span>
  )
}
