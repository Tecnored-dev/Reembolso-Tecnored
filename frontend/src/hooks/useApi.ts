import { useState, useEffect } from 'react'
import { api } from '@/services/api'
import { mensagemErro } from '@/utils'

// ---------------------------------------------------------------------------
// useApi — hook genérico para requisições GET
//
// Uso:
//   const { data, loading, error } = useApi<MeuTipo>('/meu-endpoint')
//
// O resultado fica guardado junto com a URL que o gerou: ao trocar de URL
// (ex.: outro escopo na lista), "loading" volta a ser true na hora e a resposta
// antiga não aparece por cima da nova (a requisição anterior é cancelada).
// ---------------------------------------------------------------------------
interface UseApiResult<T> {
  data: T | null
  loading: boolean
  error: string | null
}

interface Resultado<T> {
  url: string
  data: T | null
  error: string | null
}

export function useApi<T>(url: string): UseApiResult<T> {
  const [resultado, setResultado] = useState<Resultado<T> | null>(null)

  useEffect(() => {
    const controle = new AbortController()
    api
      .get<T>(url, { signal: controle.signal })
      .then((res) => setResultado({ url, data: res.data, error: null }))
      .catch((err) => {
        if (!controle.signal.aborted) setResultado({ url, data: null, error: mensagemErro(err) })
      })
    return () => controle.abort()
  }, [url])

  const atual = resultado?.url === url ? resultado : null
  return { data: atual?.data ?? null, loading: atual === null, error: atual?.error ?? null }
}
