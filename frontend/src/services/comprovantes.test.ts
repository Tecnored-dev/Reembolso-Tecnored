import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { analisarComprovante } from '@/services/comprovantes'
import type { AnaliseComprovante } from '@/types'

const RESPOSTA = { status: 'lido', origem: 'ocr', campos: {}, avisos: [] } as unknown as AnaliseComprovante

afterEach(() => {
  vi.restoreAllMocks()
})

describe('analisarComprovante', () => {
  it('envia o arquivo em multipart para a rota de análise', async () => {
    const post = vi.spyOn(api, 'post').mockResolvedValue({ data: RESPOSTA })
    const arquivo = new File(['x'], 'nota.jpg', { type: 'image/jpeg' })
    const controle = new AbortController()

    expect(await analisarComprovante(arquivo, controle.signal)).toBe(RESPOSTA)

    const [url, corpo, config] = post.mock.calls[0]
    expect(url).toBe('/api/comprovantes/analisar')
    expect((corpo as FormData).get('arquivo')).toBe(arquivo)
    expect([...(corpo as FormData).keys()]).toEqual(['arquivo'])
    expect(config?.headers).toEqual({ 'Content-Type': 'multipart/form-data' })
    expect(config?.timeout).toBe(30_000)
    expect(config?.signal).toBe(controle.signal)
  })

  it('repassa o erro da API (a tela cai no preenchimento manual)', async () => {
    const erro = { response: { status: 503, data: { detail: 'A leitura automática não está disponível agora.' } } }
    vi.spyOn(api, 'post').mockRejectedValue(erro)
    const arquivo = new File(['x'], 'nota.jpg', { type: 'image/jpeg' })
    await expect(analisarComprovante(arquivo)).rejects.toBe(erro)
  })
})
