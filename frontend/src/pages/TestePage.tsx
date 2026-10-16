import { useCallback, useEffect, useState } from 'react'
import { useContexto } from '@/components/contexto'
import { api } from '@/services/api'
import ui from '@/styles/ui.module.css'
import type { TesteEstado } from '@/types'
import { mensagemErro, rotuloPapel } from '@/utils'

// Painel de teste (só admin, só em local/hml): troca para um usuário de teste
// (colaborador, gestor, financeiro), cria pedidos de demonstração em cada etapa
// e limpa tudo o que é de teste. Pedidos de teste nunca aparecem para usuários
// reais, e vice-versa.
export default function TestePage() {
  const { config } = useContexto()
  const [estado, setEstado] = useState<TesteEstado | null>(null)
  const [msg, setMsg] = useState<{ tipo: 'ok' | 'erro'; texto: string } | null>(null)
  const [ocupado, setOcupado] = useState(false)
  const [confirmaLimpar, setConfirmaLimpar] = useState(false)

  const carregar = useCallback(async () => {
    const res = await api.get<TesteEstado>('/api/teste/estado')
    setEstado(res.data)
  }, [])

  useEffect(() => {
    carregar().catch((err) => setMsg({ tipo: 'erro', texto: mensagemErro(err) }))
  }, [carregar])

  async function executar(acao: () => Promise<string>) {
    setOcupado(true)
    setMsg(null)
    try {
      setMsg({ tipo: 'ok', texto: await acao() })
      await carregar()
    } catch (err) {
      setMsg({ tipo: 'erro', texto: mensagemErro(err) })
    } finally {
      setOcupado(false)
    }
  }

  async function verComo(email: string) {
    setOcupado(true)
    setMsg(null)
    try {
      await api.post('/api/teste/ver-como', { email })
      // Recarrega a página inteira: a sessão mudou e o menu depende dela.
      window.location.assign('/inicio')
    } catch (err) {
      setMsg({ tipo: 'erro', texto: mensagemErro(err) })
      setOcupado(false)
    }
  }

  if (!estado) return <section className={ui.card}>Carregando…</section>

  if (!estado.ativo || !estado.admin) {
    return (
      <section className={ui.card}>
        <h1 className={ui.titulo}>Painel de teste</h1>
        <p className={ui.muted}>
          {estado.ativo
            ? 'Só o admin usa o painel de teste.'
            : 'O painel de teste está desligado neste ambiente.'}
        </p>
      </section>
    )
  }

  return (
    <>
      <section className={ui.card}>
        <div className={ui.cabecalho}>
          <div>
            <h1 className={ui.titulo}>Painel de teste</h1>
            <p className={ui.muted}>
              Ambiente <strong>{config.env}</strong>. Escolha quem você quer ser; a faixa no topo
              mostra como voltar para a sua conta.
            </p>
          </div>
        </div>
        {estado.vendo_como && (
          <div className={ui.info} style={{ marginBottom: 14 }}>
            Você está vendo como <strong>{estado.vendo_como.nome}</strong>.
          </div>
        )}
        <h2 className={ui.subtitulo}>Ver como</h2>
        <div className={ui.grade}>
          {estado.usuarios.map((u) => (
            <div key={u.email} className={ui.card} style={{ marginBottom: 0 }}>
              <strong>{u.nome}</strong>
              <div className={ui.muted} style={{ margin: '4px 0 12px' }}>
                {u.papeis.map(rotuloPapel).join(' + ')} · {u.descricao}
              </div>
              <button
                className={ui.botao}
                disabled={ocupado || estado.vendo_como?.email === u.email}
                onClick={() => verComo(u.email)}
              >
                {estado.vendo_como?.email === u.email ? 'Você está aqui' : 'Entrar como'}
              </button>
            </div>
          ))}
        </div>
      </section>

      <section className={ui.card}>
        <h2 className={ui.subtitulo}>Dados de teste</h2>
        <p className={ui.muted} style={{ marginBottom: 14 }}>
          A demonstração cria 9 pedidos dos usuários de teste, um em cada etapa (conferência,
          devolvido, aprovação, pagamento, prestação, pago e recusado). Limpar apaga só os pedidos
          dos usuários de teste.
        </p>
        <div className={ui.botoes}>
          <button
            className={ui.botao}
            disabled={ocupado}
            onClick={() =>
              executar(async () => {
                const res = await api.post<{ criados: string[] }>('/api/teste/demo')
                return `Criados ${res.data.criados.length} pedidos: ${res.data.criados.join(', ')}.`
              })
            }
          >
            Criar dados de demonstração
          </button>
          {!confirmaLimpar ? (
            <button
              className={`${ui.botao} ${ui.secundario}`}
              disabled={ocupado}
              onClick={() => setConfirmaLimpar(true)}
            >
              Limpar dados de teste
            </button>
          ) : (
            <>
              <button
                className={`${ui.botao} ${ui.perigo}`}
                disabled={ocupado}
                onClick={() => {
                  setConfirmaLimpar(false)
                  void executar(async () => {
                    const res = await api.post<{ apagados: number }>('/api/teste/limpar')
                    return `${res.data.apagados} pedido(s) de teste apagado(s).`
                  })
                }}
              >
                Confirmar: apagar pedidos de teste
              </button>
              <button className={`${ui.botao} ${ui.secundario}`} onClick={() => setConfirmaLimpar(false)}>
                Cancelar
              </button>
            </>
          )}
        </div>
        {msg && (
          <div className={msg.tipo === 'ok' ? ui.info : ui.erro} style={{ marginTop: 14 }}>
            {msg.texto}
          </div>
        )}
      </section>
    </>
  )
}
