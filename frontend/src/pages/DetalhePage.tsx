import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import StatusBadge from '@/components/StatusBadge'
import { api } from '@/services/api'
import ui from '@/styles/ui.module.css'
import type { Solicitacao, Status } from '@/types'
import { formatarData, formatarDataHora, formatarMoeda, hojeISO, mensagemErro } from '@/utils'
import styles from './DetalhePage.module.css'

const ACAO_HISTORICO: Record<string, string> = {
  enviado: 'Enviou',
  reenviado: 'Corrigiu e reenviou',
  conferido: 'Conferiu',
  aprovado: 'Aprovou',
  devolvido: 'Devolveu para correção',
  pago: 'Registrou o pagamento',
  cancelado: 'Cancelou',
}

// Etapas mostradas no topo — o "status do reembolso" que evita cobrar a Thais.
function etapas(s: Solicitacao): { rotulo: string; feita: boolean; atual: boolean }[] {
  const ordem: Status[] = ['em_conferencia', 'aguardando_gestor', 'aguardando_pagamento', 'pago']
  const lista = [
    { chave: 'enviada', rotulo: 'Enviada' },
    { chave: 'em_conferencia', rotulo: 'Conferência' },
    ...(s.pula_gestor ? [] : [{ chave: 'aguardando_gestor', rotulo: 'Gestor' }]),
    { chave: 'aguardando_pagamento', rotulo: 'Pagamento' },
    { chave: 'pago', rotulo: 'Paga' },
  ]
  // Devolvida volta para a conferência; cancelada para onde parou.
  const efetivo = s.status === 'devolvido' || s.status === 'cancelado' ? 'em_conferencia' : s.status
  const posicao = ordem.indexOf(efetivo as Status)
  return lista.map((e) => {
    const idx = e.chave === 'enviada' ? -1 : ordem.indexOf(e.chave as Status)
    return {
      rotulo: e.rotulo,
      feita: idx < posicao || (s.status === 'pago' && e.chave === 'pago'),
      atual: idx === posicao && s.status !== 'pago',
    }
  })
}

export default function DetalhePage() {
  const { id } = useParams()
  const location = useLocation()
  const [sol, setSol] = useState<Solicitacao | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [anexoUrl, setAnexoUrl] = useState<string | null>(null)
  const [comentario, setComentario] = useState('')
  const [dataPagamento, setDataPagamento] = useState(hojeISO())
  const [processando, setProcessando] = useState(false)
  const [erroAcao, setErroAcao] = useState<string | null>(null)
  const navigate = useNavigate()
  // Aviso de "Enviado!" só na chegada: limpa o state para não reaparecer no F5.
  const [enviadoAgora] = useState(
    Boolean((location.state as { enviado?: boolean } | null)?.enviado)
  )
  useEffect(() => {
    if (location.state) navigate(location.pathname, { replace: true, state: null })
  }, [location.state, location.pathname, navigate])

  const carregar = useCallback(() => {
    api
      .get<Solicitacao>(`/api/solicitacoes/${id}`)
      .then((r) => setSol(r.data))
      .catch((e) => setErro(mensagemErro(e)))
  }, [id])

  useEffect(carregar, [carregar])

  // A nota vem da API com o cookie de sessão; vira um blob local para exibir.
  // Alimentação tem uma nota e ela abre direto; em viagem, a pessoa escolhe qual ver.
  const viagem = sol?.tipo === 'viagem'
  const [notaAberta, setNotaAberta] = useState<number | null>(null)
  const despesa = viagem
    ? sol?.despesas.find((d) => d.id === notaAberta)
    : sol?.despesas[0]
  useEffect(() => {
    setAnexoUrl(null)
    if (!sol || !despesa) return
    let url: string | null = null
    api
      .get(`/api/solicitacoes/${sol.id}/despesas/${despesa.id}/arquivo`, { responseType: 'blob' })
      .then((r) => {
        url = URL.createObjectURL(r.data as Blob)
        setAnexoUrl(url)
      })
      .catch(() => setAnexoUrl(null))
    return () => {
      if (url) URL.revokeObjectURL(url)
    }
  }, [sol, despesa])

  async function agir(caminho: string, corpo: object) {
    setErroAcao(null)
    setProcessando(true)
    try {
      const r = await api.post<Solicitacao>(`/api/solicitacoes/${id}/${caminho}`, corpo)
      setSol(r.data)
      setComentario('')
    } catch (e) {
      setErroAcao(mensagemErro(e))
    } finally {
      setProcessando(false)
    }
  }

  if (erro) return <div className={ui.erro}>{erro}</div>
  if (!sol) return <p className={ui.muted}>Carregando…</p>

  const decisao = sol.acoes.includes('conferir') ? 'conferir' : sol.acoes.includes('aprovar') ? 'aprovar' : null

  return (
    <>
      {enviadoAgora && (
        <div className={ui.info} style={{ marginBottom: 16 }}>
          Enviado! Acompanhe o andamento por aqui — você também recebe um aviso a cada etapa.
        </div>
      )}

      <section className={ui.card}>
        <div className={ui.cabecalho}>
          <div>
            <h1 className={ui.titulo}>
              {sol.codigo} <StatusBadge status={sol.status} />
            </h1>
            <p className={ui.muted}>
              {sol.tipo_rotulo} · enviada em {formatarDataHora(sol.enviado_em)} · {sol.status_rotulo}
            </p>
          </div>
          <div className={styles.valor}>{formatarMoeda(sol.valor_total, sol.moeda)}</div>
        </div>

        {sol.status !== 'cancelado' && (
          <ol className={styles.etapas} aria-label="Andamento">
            {etapas(sol).map((e) => (
              <li
                key={e.rotulo}
                className={e.feita ? styles.feita : e.atual ? styles.atual : undefined}
              >
                {e.rotulo}
              </li>
            ))}
          </ol>
        )}

        {sol.status === 'devolvido' && (
          <div className={ui.aviso} style={{ marginTop: 16 }}>
            <strong>Devolvida por {sol.devolvido_por}:</strong> {sol.motivo_devolucao}
            {sol.acoes.includes('reenviar') && (
              <div style={{ marginTop: 10 }}>
                <Link
                  to={`/solicitacoes/${sol.id}/${viagem ? 'corrigir-viagem' : 'corrigir'}`}
                  className={ui.botao}
                >
                  Corrigir e reenviar
                </Link>
              </div>
            )}
          </div>
        )}
        {sol.status === 'cancelado' && (
          <div className={ui.aviso} style={{ marginTop: 16 }}>
            Cancelada: {sol.motivo_cancelamento}
          </div>
        )}
        {sol.alerta_limite && (
          <div className={ui.aviso} style={{ marginTop: 12 }}>
            ⚠️ {sol.alerta_limite}
          </div>
        )}
      </section>

      {decisao && (
        <section className={`${ui.card} ${styles.acoes}`}>
          <h2 className={ui.subtitulo}>
            {decisao === 'conferir' ? 'Conferência do financeiro' : 'Sua aprovação'}
          </h2>
          <p className={ui.muted} style={{ marginBottom: 12 }}>
            {decisao === 'conferir'
              ? 'Confira os dados e a nota. Se estiver tudo certo, segue para o gestor (ou direto para pagamento, se o solicitante for gestor).'
              : 'O financeiro já conferiu a nota. Aprove ou devolva para correção.'}
          </p>
          <div className={ui.campo}>
            <label htmlFor="comentario">Comentário (obrigatório para devolver)</label>
            <textarea
              id="comentario"
              value={comentario}
              maxLength={1000}
              onChange={(e) => setComentario(e.target.value)}
            />
          </div>
          {erroAcao && <div className={ui.erro} style={{ marginTop: 12 }}>{erroAcao}</div>}
          <div className={ui.botoes} style={{ marginTop: 12 }}>
            <button
              className={ui.botao}
              disabled={processando}
              onClick={() => agir(decisao, { aprovar: true, comentario: comentario || null })}
            >
              {decisao === 'conferir' ? 'Conferido — enviar adiante' : 'Aprovar'}
            </button>
            <button
              className={`${ui.botao} ${ui.perigo}`}
              disabled={processando || !comentario.trim()}
              onClick={() => agir(decisao, { aprovar: false, comentario })}
            >
              Devolver para correção
            </button>
          </div>
        </section>
      )}

      {sol.acoes.includes('pagar') && (
        <section className={`${ui.card} ${styles.acoes}`}>
          <h2 className={ui.subtitulo}>Registrar pagamento</h2>
          <div className={ui.botoes}>
            <div className={ui.campo}>
              <label htmlFor="dataPagamento">Data do pagamento</label>
              <input
                id="dataPagamento"
                type="date"
                value={dataPagamento}
                onChange={(e) => setDataPagamento(e.target.value)}
              />
            </div>
            <button
              className={ui.botao}
              style={{ alignSelf: 'flex-end' }}
              disabled={processando || !dataPagamento}
              onClick={() => agir('pagar', { data_pagamento: dataPagamento })}
            >
              Marcar como paga
            </button>
          </div>
          {erroAcao && <div className={ui.erro} style={{ marginTop: 12 }}>{erroAcao}</div>}
        </section>
      )}

      <div className={styles.colunas}>
        <section className={ui.card}>
          <h2 className={ui.subtitulo}>Dados</h2>
          <dl className={ui.dados}>
            <div>
              <dt>Solicitante</dt>
              <dd>{sol.solicitante_nome}</dd>
            </div>
            <div>
              <dt>Matrícula</dt>
              <dd>{sol.matricula}</dd>
            </div>
            <div>
              <dt>Centro de custo</dt>
              <dd>{sol.centro_custo}</dd>
            </div>
            <div>
              <dt>Empresa de débito</dt>
              <dd>{sol.empresa}</dd>
            </div>
            <div>
              <dt>Gestor</dt>
              <dd>{sol.pula_gestor ? 'Não se aplica (solicitante é gestor)' : sol.gestor_nome}</dd>
            </div>
            {viagem ? (
              <>
                <div>
                  <dt>Destino</dt>
                  <dd>{sol.destino}</dd>
                </div>
                <div>
                  <dt>Período</dt>
                  <dd>
                    {formatarData(sol.viagem_inicio)} a {formatarData(sol.viagem_fim)}
                  </dd>
                </div>
              </>
            ) : (
              <div>
                <dt>Data da despesa</dt>
                <dd>{formatarData(sol.despesas[0]?.data_despesa ?? null)}</dd>
              </div>
            )}
            {sol.data_pagamento && (
              <div>
                <dt>Pago em</dt>
                <dd>{formatarData(sol.data_pagamento)}</dd>
              </div>
            )}
            <div style={{ gridColumn: '1 / -1' }}>
              <dt>{viagem ? 'Motivo da viagem' : 'Descrição'}</dt>
              <dd>{sol.descricao}</dd>
            </div>
          </dl>
        </section>

        <section className={ui.card}>
          <h2 className={ui.subtitulo}>Nota</h2>
          {viagem && !despesa && <p className={ui.muted}>Escolha uma nota na lista abaixo.</p>}
          {viagem && despesa && (
            <p className={ui.muted} style={{ marginBottom: 8 }}>
              {despesa.categoria_rotulo} · {formatarData(despesa.data_despesa)} ·{' '}
              {formatarMoeda(despesa.valor, sol.moeda)}
            </p>
          )}
          {despesa && !anexoUrl && <p className={ui.muted}>Carregando a nota…</p>}
          {anexoUrl && despesa?.arquivo_tipo.startsWith('image/') && (
            <a href={anexoUrl} target="_blank" rel="noreferrer">
              <img src={anexoUrl} alt={`Nota ${sol.codigo}`} className={styles.nota} />
            </a>
          )}
          {anexoUrl && despesa?.arquivo_tipo === 'application/pdf' && (
            <a href={anexoUrl} target="_blank" rel="noreferrer" className={`${ui.botao} ${ui.secundario}`}>
              Abrir PDF ({despesa.arquivo_nome})
            </a>
          )}
        </section>
      </div>

      {viagem && (
        <section className={ui.card}>
          <h2 className={ui.subtitulo}>Notas ({sol.despesas.length})</h2>
          <div style={{ overflowX: 'auto' }}>
            <table className={ui.tabela}>
              <thead>
                <tr>
                  <th>Categoria</th>
                  <th>Data</th>
                  <th className={ui.opcional}>Descrição</th>
                  <th className={ui.direita}>Valor</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {sol.despesas.map((d) => (
                  <tr key={d.id} onClick={() => setNotaAberta(d.id)}>
                    <td>{d.categoria_rotulo}</td>
                    <td>{formatarData(d.data_despesa)}</td>
                    <td className={ui.opcional}>{d.descricao ?? '—'}</td>
                    <td className={ui.direita}>{formatarMoeda(d.valor, sol.moeda)}</td>
                    <td className={ui.direita}>
                      <button
                        type="button"
                        className={`${ui.botao} ${ui.secundario}`}
                        aria-pressed={notaAberta === d.id}
                        onClick={(e) => {
                          e.stopPropagation()
                          setNotaAberta(d.id)
                        }}
                      >
                        {notaAberta === d.id ? 'Aberta' : 'Ver nota'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className={ui.card}>
        <h2 className={ui.subtitulo}>Histórico</h2>
        <ul className={styles.historico}>
          {[...sol.historico].reverse().map((h, i) => (
            <li key={i}>
              <div>
                <strong>{h.usuario_nome}</strong> — {ACAO_HISTORICO[h.acao] ?? h.acao}
                {h.comentario && <div className={styles.comentario}>“{h.comentario}”</div>}
              </div>
              <span className={ui.muted}>{formatarDataHora(h.criado_em)}</span>
            </li>
          ))}
        </ul>
      </section>
    </>
  )
}
