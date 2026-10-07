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

/** "45.90" → "R$ 45,90" */
export function formatarMoeda(valor: string | number, moeda = 'BRL'): string {
  const numero = typeof valor === 'string' ? Number(valor) : valor
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: moeda }).format(numero)
}

/** "2026-10-06" → "06/10/2026" (sem passar por Date, para não sofrer com fuso). */
export function formatarData(iso: string | null): string {
  if (!iso) return '—'
  const [ano, mes, dia] = iso.slice(0, 10).split('-')
  return `${dia}/${mes}/${ano}`
}

/** Datas da API vêm em UTC sem fuso ("2026-10-06T14:05:00"); mostra no horário local. */
export function formatarDataHora(iso: string | null): string {
  if (!iso) return '—'
  const data = new Date(iso.endsWith('Z') ? iso : `${iso}Z`)
  return data.toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** Data de hoje no fuso local, no formato do <input type="date">. */
export function hojeISO(): string {
  const d = new Date()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

/** Mensagem de erro amigável a partir de um erro do axios. */
export function mensagemErro(err: unknown): string {
  const e = err as { response?: { data?: { detail?: unknown } }; message?: string }
  const detail = e.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return 'Confira os campos preenchidos.'
  return e.message ?? 'Erro inesperado.'
}

/** "1.234,56" / "45.90" → número (NaN se inválido). Mesma leitura da API. */
export function lerValor(texto: string): number {
  let bruto = texto.replace(/R\$|\s/g, '')
  if (bruto.includes(',')) bruto = bruto.replace(/\./g, '').replace(',', '.')
  return bruto === '' ? NaN : Number(bruto)
}

/**
 * Destino interno seguro para o parâmetro `?voltar=`. Só aceita caminho do
 * próprio site: começa com uma barra e não tem `//` nem `\` no início (o
 * navegador trata `/\site` como `//site`, ou seja, outro domínio).
 */
export function caminhoInterno(pedido: string | null, padrao = '/inicio'): string {
  if (!pedido || !pedido.startsWith('/')) return padrao
  if (pedido.startsWith('//') || pedido.includes('\\')) return padrao
  return pedido
}
