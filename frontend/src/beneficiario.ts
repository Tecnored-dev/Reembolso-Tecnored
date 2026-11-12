// Pedido em nome de outra pessoa (Thais, 13/10/2026): o reembolso vai para o
// beneficiário e quem aprova é o gestor dele.
import type { Gestor, UsuarioBusca } from '@/types'

export interface BeneficiarioForm {
  ativo: boolean
  email: string
  nome: string
  matricula: string
  /** Colega encontrado na busca (já entrou no sistema). */
  conhecido: UsuarioBusca | null
}

export const BENEFICIARIO_VAZIO: BeneficiarioForm = {
  ativo: false,
  email: '',
  nome: '',
  matricula: '',
  conhecido: null,
}

/** Precisa digitar nome e matrícula? (a pessoa nunca entrou). O centro de
 * custo é escolhido no próprio pedido (Thais, 15/10). */
export function precisaDosDados(b: BeneficiarioForm): boolean {
  return b.ativo && !b.conhecido?.perfil_completo
}

/** A pessoa do pedido é gestor? Então não há aprovação de gestor. */
export function beneficiarioEhGestor(b: BeneficiarioForm, gestores: Gestor[]): boolean {
  const email = b.email.trim().toLowerCase()
  return Boolean(b.conhecido?.eh_gestor) || gestores.some((g) => g.email === email)
}

/** Campos que vão para a API (vazio quando é um pedido para si mesmo). */
export function camposBeneficiario(b: BeneficiarioForm): Record<string, string> {
  if (!b.ativo || !b.email.trim()) return {}
  const campos: Record<string, string> = { beneficiario_email: b.email.trim() }
  if (precisaDosDados(b)) {
    campos.beneficiario_nome = b.nome
    campos.beneficiario_matricula = b.matricula
  }
  return campos
}
