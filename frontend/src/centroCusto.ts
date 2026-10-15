// Centro de custo do pedido (Thais, 15/10): escolhido em cada pedido.
import type { Opcao, Perfil, Solicitacao } from '@/types'

/** Valor inicial: na correção, o do pedido; num pedido novo, o último usado. */
export function centroCustoInicial(
  centros: Opcao[],
  perfil: Perfil,
  original: Solicitacao | null
): string {
  const achado = original
    ? centros.find((c) => c.rotulo === original.centro_custo)
    : centros.find((c) => c.id === perfil.centro_custo?.id)
  return achado ? String(achado.id) : ''
}
