import { api } from '@/services/api'
import type { AnaliseComprovante } from '@/types'

// ---------------------------------------------------------------------------
// Leitura automática do comprovante (OCR no servidor). Só sugere o
// preenchimento: não grava nada nem cria pedido. Se falhar, o colaborador
// preenche à mão, como antes.
// ---------------------------------------------------------------------------

// Um PDF digitalizado leva até ~15 s no servidor, mais a espera por vaga e o
// upload pelo celular: folga acima dos 20 s padrão do axios.
const TEMPO_LIMITE = 30_000

export async function analisarComprovante(
  arquivo: File,
  signal?: AbortSignal
): Promise<AnaliseComprovante> {
  const form = new FormData()
  form.append('arquivo', arquivo)
  // multipart explícito: sem isso o axios converteria o FormData em JSON.
  const res = await api.post<AnaliseComprovante>('/api/comprovantes/analisar', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: TEMPO_LIMITE,
    signal,
  })
  return res.data
}
