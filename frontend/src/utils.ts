import type { AppConfig, Papel } from '@/types'

/** "vX.Y.Z+hash (data)" — cada parte opcional só aparece se existir. */
export function formatVersion(config: AppConfig | null): string | null {
  if (!config?.version) return null
  let text = `v${config.version}`
  if (config.commit_hash) text += `+${config.commit_hash}`
  if (config.released_at) text += ` (${config.released_at})`
  return text
}

const ROTULO_PAPEL: Record<Papel, string> = {
  colaborador: 'Colaborador',
  gestor: 'Gestor',
  financeiro: 'Financeiro',
  admin: 'Admin',
}

export function rotuloPapel(papel: Papel): string {
  return ROTULO_PAPEL[papel] ?? papel
}
