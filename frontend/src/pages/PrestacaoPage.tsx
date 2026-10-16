import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import NotasViagem from '@/components/NotasViagem'
import { useApi } from '@/hooks/useApi'
import { anexarNotas, conferirNotas, novaNota, notasEnviadas, type NotaForm } from '@/notas'
import { api } from '@/services/api'
import ui from '@/styles/ui.module.css'
import type { Cadastros, Solicitacao } from '@/types'
import { formatarData, formatarMoeda, hojeISO, mensagemErro, somarValores } from '@/utils'

// Prestação de contas do adiantamento: depois da viagem, o colaborador manda as
// notas do que gastou. O financeiro confere; se sobrou, o colaborador devolve;
// se faltou, recebe a diferença (com aprovação do gestor).
export default function PrestacaoPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: cadastros } = useApi<Cadastros>('/api/cadastros')
  const [sol, setSol] = useState<Solicitacao | null>(null)
  const [erroCarga, setErroCarga] = useState<string | null>(null)
  const [notas, setNotas] = useState<NotaForm[]>(() => [novaNota()])
  const [erro, setErro] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    api
      .get<Solicitacao>(`/api/solicitacoes/${id}`)
      .then((r) => {
        setSol(r.data)
        const enviadas = notasEnviadas(r.data.despesas)
        if (enviadas.length) setNotas(enviadas)
      })
      .catch((e) => setErroCarga(mensagemErro(e)))
  }, [id])

  const gasto = useMemo(() => somarValores(notas.map((n) => n.valor)), [notas])

  async function enviar(e: FormEvent) {
    e.preventDefault()
    setErro(null)
    const problema = conferirNotas(notas)
    if (problema) {
      setErro(problema)
      return
    }
    const form = new FormData()
    anexarNotas(form, notas)
    setEnviando(true)
    try {
      // multipart explícito: sem isso o axios converteria o FormData em JSON.
      const res = await api.post<Solicitacao>(`/api/solicitacoes/${id}/prestacao`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      navigate(`/solicitacoes/${res.data.id}`, { replace: true, state: { enviado: true } })
    } catch (err) {
      setErro(mensagemErro(err))
    } finally {
      setEnviando(false)
    }
  }

  if (erroCarga) return <div className={ui.erro}>{erroCarga}</div>
  if (!sol) return <p className={ui.muted}>Carregando…</p>
  if (!sol.acoes.includes('prestar_contas')) {
    return (
      <section className={ui.card}>
        <div className={ui.aviso}>Esta solicitação não está aguardando prestação de contas.</div>
      </section>
    )
  }

  const adiantado = Number(sol.valor_total)
  const diferenca = adiantado - gasto
  const corrigindo = sol.status === 'prestacao_devolvida'

  return (
    <section className={ui.card}>
      <div className={ui.cabecalho}>
        <div>
          <h1 className={ui.titulo}>
            {corrigindo ? 'Corrigir a prestação de contas' : 'Prestação de contas'} · {sol.codigo}
          </h1>
          <p className={ui.muted}>
            {sol.destino} · {formatarData(sol.viagem_inicio)} a {formatarData(sol.viagem_fim)}
          </p>
        </div>
      </div>

      {corrigindo && sol.motivo_devolucao && (
        <div className={ui.aviso} style={{ marginBottom: 16 }}>
          <strong>Devolvida por {sol.devolvido_por}:</strong> {sol.motivo_devolucao}
        </div>
      )}

      <form className={ui.form} onSubmit={enviar}>
        <p className={ui.muted}>
          Anexe as notas de tudo o que você gastou na viagem. Adiantado:{' '}
          <strong>{formatarMoeda(adiantado)}</strong>
          {sol.diarias !== null && (
            <>
              {' '}
              ({`${sol.diarias} diária${sol.diarias === 1 ? '' : 's'}`}
              {sol.valor_complementar !== null && ' + diária complementar'})
            </>
          )}
          .
          {sol.prazo_prestacao && <> Prazo: até {formatarData(sol.prazo_prestacao)}.</>}
        </p>
        {sol.prazo_prestacao && sol.prazo_prestacao < hojeISO() && !corrigindo && (
          <div className={ui.aviso}>O prazo da prestação de contas já venceu. Envie as notas o quanto antes.</div>
        )}

        <NotasViagem notas={notas} setNotas={setNotas} cadastros={cadastros} />

        <div className={ui.info} aria-live="polite">
          {diferenca > 0.004 && (
            <>
              <strong>Sobra de {formatarMoeda(diferenca)}.</strong> Depois da conferência você
              devolve esse valor por transferência (o financeiro passa os dados) e anexa o
              comprovante aqui no sistema.
            </>
          )}
          {diferenca < -0.004 && (
            <>
              <strong>Você gastou {formatarMoeda(-diferenca)} a mais.</strong> Depois da
              conferência, a diferença vai para a aprovação do gestor e o financeiro paga.
            </>
          )}
          {Math.abs(diferenca) <= 0.004 && (
            <strong>O gasto bate com o adiantamento: depois da conferência, encerra.</strong>
          )}
        </div>

        {erro && <div className={ui.erro}>{erro}</div>}

        <div className={`${ui.botoes} ${ui.barraAcao}`}>
          <button className={ui.botao} disabled={enviando}>
            {enviando ? 'Enviando…' : 'Enviar para conferência'}
          </button>
          <Link to={`/solicitacoes/${sol.id}`} className={`${ui.botao} ${ui.secundario}`}>
            Cancelar
          </Link>
        </div>
      </form>
    </section>
  )
}
