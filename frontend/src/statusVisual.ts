import type { NomeIcone } from '@/components/Icone'
import type { Status } from '@/types'

export const CURTO: Record<Status, string> = {
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
export type Familia = 'voce' | 'financeiro' | 'gestor' | 'concluido' | 'cancelado' | 'recusado'

export const VISUAL: Record<Status, { familia: Familia; icone: NomeIcone }> = {
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

// Quem está com o pedido e o que acontece agora, na voz de quem pediu.
// Derivado só do status (e do nome do gestor): não existe campo novo na API.
export function comQuemEsta(status: Status, gestorNome?: string | null): { quem: string; frase: string } {
  switch (status) {
    case 'devolvido':
    case 'prestacao_devolvida':
      return { quem: 'Com você', frase: 'Corrija e reenvie.' }
    case 'aguardando_prestacao':
      return { quem: 'Com você', frase: 'Envie as notas da viagem.' }
    case 'aguardando_devolucao':
      return { quem: 'Com você', frase: 'Devolva a sobra e anexe o comprovante.' }
    case 'em_conferencia':
    case 'prestacao_em_conferencia':
    case 'devolucao_em_conferencia':
      return { quem: 'Com o financeiro', frase: 'O financeiro está conferindo.' }
    case 'aguardando_pagamento':
    case 'diferenca_aguardando_pagamento':
      return { quem: 'Com o financeiro', frase: 'Aprovado, falta pagar.' }
    case 'aguardando_gestor':
    case 'diferenca_aguardando_gestor':
      return {
        quem: gestorNome ? `Com ${gestorNome}` : 'Com o gestor',
        frase: 'Aguardando a aprovação do gestor.',
      }
    case 'pago':
    case 'encerrado':
      return { quem: 'Concluído', frase: 'Nada a fazer.' }
    case 'recusado':
      return { quem: 'Finalizado', frase: 'Recusado pelo gestor.' }
    case 'cancelado':
      return { quem: 'Cancelada', frase: 'Este pedido foi cancelado.' }
  }
}
