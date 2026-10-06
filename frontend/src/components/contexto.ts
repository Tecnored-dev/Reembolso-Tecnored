import { useOutletContext } from 'react-router-dom'
import type { AppConfig, Papel, Perfil, Session } from '@/types'

export interface Contexto {
  session: Session
  config: AppConfig
  perfil: Perfil
  recarregarPerfil: () => Promise<void>
  tem: (papel: Papel) => boolean
}

/** Dados do usuário logado, para as páginas dentro do Layout. */
export function useContexto(): Contexto {
  return useOutletContext<Contexto>()
}
