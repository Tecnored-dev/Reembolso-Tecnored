import type { Status } from '@/types'

// A partir de quantos dias parado o pedido ganha destaque (âmbar).
export const DIAS_ALERTA = 5

const FINAIS: Status[] = ['pago', 'encerrado', 'cancelado', 'recusado']

/** Pedido que ainda está andando (não terminou nem foi cancelado/recusado). */
export function emAndamento(status: Status): boolean {
  return !FINAIS.includes(status)
}

/** Dias inteiros desde a última movimentação (nunca negativo). A API manda UTC
 * sem fuso ("2026-10-06T14:05:00"); sem o "Z" o navegador leria como horário
 * local e, no Brasil, o pedido pareceria parado 3 horas a menos. */
export function diasDesde(iso: string, agora: Date = new Date()): number {
  const temFuso = /(Z|[+-]\d\d:?\d\d)$/i.test(iso)
  const desde = new Date(temFuso ? iso : `${iso}Z`).getTime()
  if (Number.isNaN(desde)) return 0
  return Math.max(0, Math.floor((agora.getTime() - desde) / 86_400_000))
}

/** "hoje", "há 1 dia" ou "há N dias". */
export function textoParado(dias: number): string {
  if (dias <= 0) return 'hoje'
  return dias === 1 ? 'há 1 dia' : `há ${dias} dias`
}
