import { useState, useEffect, useCallback } from 'react'
import { api } from '@/services/api'
import type { AxiosRequestConfig } from 'axios'

// ---------------------------------------------------------------------------
// useApi — hook genérico para requisições GET
//
// Uso:
//   const { data, loading, error, refetch } = useApi<MeuTipo>('/meu-endpoint')
// ---------------------------------------------------------------------------
interface UseApiResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  refetch: () => void
}

export function useApi<T>(
  url: string,
  config?: AxiosRequestConfig
): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(() => {
    setLoading(true)
    setError(null)

    api
      .get<T>(url, config)
      .then((res) => setData(res.data))
      .catch((err) => {
        const message =
          err.response?.data?.detail ?? err.message ?? 'Erro desconhecido'
        setError(message)
      })
      .finally(() => setLoading(false))
  }, [url]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetchData()
  }, [fetchData])

  return { data, loading, error, refetch: fetchData }
}
