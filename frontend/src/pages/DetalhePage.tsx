import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useContexto } from '@/components/contexto'
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
  prestacao_enviada: 'Enviou a prestação de contas',
  prestacao_reenviada: 'Corrigiu e reenviou a prestação de contas',
  prestacao_conferida: 'Conferiu a prestação de contas',
  comprovante_enviado: 'Enviou o comprovante da devolução',
  comprovante_recusado: 'Recusou o comprovante',
  devolucao_confirmada: 'Confirmou o recebimento da devolução',
  diferenca_aprovada: 'Aprovou a diferença',
  diferenca_paga: 'Pagou a diferença',
}

interface Etapa {
  rotulo: string
  feita: boolean
  atual: boolean
}

// Adiantamento: pedido → gestor → pagamento → prestação → conferência → acerto → fim.
const POSICAO_ADIANTAMENTO: Partial<Record<Status, number>> = {
  aguardando_gestor: 0,
  devolvido: 0,
  aguardando_pagamento: 1,
  aguardando_prestacao: 2,
  prestacao_devolvida: 2,
  prestacao_em_conferencia: 3,
  aguardando_devolucao: 4,
  devolucao_em_conferencia: 4,
  diferenca_aguardando_gestor: 4,
  diferenca_aguardando_pagamento: 4,
  encerrado: 5,
}

function etapasAdiantamento(s: Solicitacao): Etapa[] {
  const lista = [
    { rotulo: 'Pedido', idx: -1 },
    ...(s.pula_gestor ? [] : [{ rotulo: 'Gestor', idx: 0 }]),
    { rotulo: 'Pagamento', idx: 1 },
    { rotulo: 'Prestação de contas', idx: 2 },
    { rotulo: 'Conferência', idx: 3 },
    { rotulo: 'Acerto', idx: 4 },
    { rotulo: 'Encerrada', idx: 5 },
  ]
  const posicao = POSICAO_ADIANTAMENTO[s.status] ?? 0
  const fim = s.status === 'encerrado'
  return lista.map((e) => ({
    rotulo: e.rotulo,
    feita: e.idx < posicao || (fim && e.idx === 5),
    atual: e.idx === posicao && !fim,
  }))
}

// Etapas mostradas no topo — o "status do reembolso" que evita cobrar a Thais.
function etapas(s: Solicitacao): Etapa[] {
  if (s.tipo === 'adiantamento') return etapasAdiantamento(s)
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
  const [dataTransferencia, setDataTransferencia] = useState(hojeISO())
  const [comprovante, setComprovante] = useState<File | null>(null)
  const navigate = useNavigate()
  const { session, tem } = useContexto()
  const usuarioEmail = session.email
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
  // Alimentação tem uma nota e ela abre direto; em viagem e na prestação de
  // contas do adiantamento, a pessoa escolhe qual ver.
  const viagem = sol?.tipo === 'viagem'
  const adiantamento = sol?.tipo === 'adiantamento'
  const variasNotas = viagem || adiantamento
  const [notaAberta, setNotaAberta] = useState<number | null>(null)
  const despesa = variasNotas
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

  async function enviarComprovante(e: FormEvent) {
    e.preventDefault()
    if (!comprovante) {
      setErroAcao('Anexe o comprovante da transferência.')
      return
    }
    const form = new FormData()
    form.append('data_transferencia', dataTransferencia)
    form.append('arquivo', comprovante)
    setErroAcao(null)
    setProcessando(true)
    try {
      const r = await api.post<Solicitacao>(`/api/solicitacoes/${id}/comprovante`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setSol(r.data)
      setComprovante(null)
    } catch (err) {
      setErroAcao(mensagemErro(err))
    } finally {
      setProcessando(false)
    }
  }

  if (erro) return <div className={ui.erro}>{erro}</div>
  if (!sol) return <p className={ui.muted}>Carregando…</p>

  const decisao = sol.acoes.includes('conferir') ? 'conferir' : sol.acoes.includes('aprovar') ? 'aprovar' : null
  const notas = sol.despesas.filter((d) => d.categoria !== 'comprovante_devolucao')
  const comprovanteEnviado = sol.despesas.find((d) => d.categoria === 'comprovante_devolucao')
  const saldo = sol.saldo === null ? null : Number(sol.saldo)
  const linkCorrecao = viagem ? 'corrigir-viagem' : adiantamento ? 'corrigir-adiantamento' : 'corrigir'
  const textoDecisao = (() => {
    if (decisao === 'conferir' && sol.status === 'prestacao_em_conferencia')
      return {
        titulo: 'Conferência da prestação de contas',
        texto: `Confira as notas. Adiantado ${formatarMoeda(sol.valor_total)}, gasto ${formatarMoeda(
          sol.valor_gasto ?? 0
        )}: ${resumoSaldo(saldo)}`,
        ok: 'Conferida — seguir',
      }
    if (decisao === 'conferir')
      return {
        titulo: 'Conferência do financeiro',
        texto:
          'Confira os dados e a nota. Se estiver tudo certo, segue para o gestor (ou direto para pagamento, se o solicitante for gestor).',
        ok: 'Conferido — enviar adiante',
      }
    if (sol.status === 'diferenca_aguardando_gestor')
      return {
        titulo: 'Aprovar a diferença',
        texto: `${sol.solicitante_nome} gastou ${formatarMoeda(
          -(saldo ?? 0)
        )} a mais que o adiantado. O financeiro já conferiu as notas. Aprove a diferença ou devolva para correção.`,
        ok: 'Aprovar a diferença',
      }
    if (adiantamento)
      return {
        titulo: 'Sua aprovação',
        texto: `Adiantamento de ${sol.diarias} diária(s)${
          sol.valor_complementar !== null
            ? ` + diária complementar de ${formatarMoeda(sol.valor_complementar)} (quem recebe auxílio refeição)`
            : ''
        } para ${sol.destino}, pago antes da viagem. Depois, o colaborador presta contas com as notas.`,
        ok: 'Aprovar',
      }
    return {
      titulo: 'Sua aprovação',
      texto: 'O financeiro já conferiu a nota. Aprove ou devolva para correção.',
      ok: 'Aprovar',
    }
  })()

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
            {sol.criado_por_nome && (
              <p className={ui.muted}>
                Pedido por <strong>{sol.criado_por_nome}</strong> em nome de{' '}
                <strong>{sol.solicitante_nome}</strong>
              </p>
            )}
          </div>
          <div className={styles.valor}>
            {adiantamento && <span className={styles.valorRotulo}>Adiantado</span>}
            {formatarMoeda(sol.valor_total, sol.moeda)}
          </div>
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
                <Link to={`/solicitacoes/${sol.id}/${linkCorrecao}`} className={ui.botao}>
                  Corrigir e reenviar
                </Link>
              </div>
            )}
          </div>
        )}
        {sol.acoes.includes('prestar_contas') && (
          <div className={sol.status === 'prestacao_devolvida' ? ui.aviso : ui.info} style={{ marginTop: 16 }}>
            {sol.status === 'prestacao_devolvida' ? (
              <>
                <strong>Prestação devolvida por {sol.devolvido_por}:</strong> {sol.motivo_devolucao}
              </>
            ) : (
              <>
                O adiantamento foi pago. <strong>Depois da viagem</strong>, preste contas com as
                notas do que você gastou
                {sol.prazo_prestacao && <> (prazo: até {formatarData(sol.prazo_prestacao)})</>}.
              </>
            )}
            <div style={{ marginTop: 10 }}>
              <Link to={`/solicitacoes/${sol.id}/prestar-contas`} className={ui.botao}>
                {sol.status === 'prestacao_devolvida' ? 'Corrigir a prestação de contas' : 'Prestar contas'}
              </Link>
            </div>
          </div>
        )}
        {sol.status === 'aguardando_devolucao' && !sol.acoes.includes('enviar_comprovante') && (
          <div className={ui.info} style={{ marginTop: 16 }}>
            Sobrou {formatarMoeda(saldo ?? 0)}: aguardando o colaborador devolver por transferência.
          </div>
        )}
        {sol.status === 'encerrado' && saldo !== null && (
          <div className={ui.info} style={{ marginTop: 16 }}>
            Encerrada. {resumoSaldo(saldo, true)}
          </div>
        )}
        {sol.status === 'aguardando_prestacao' &&
          !sol.acoes.includes('prestar_contas') &&
          sol.prazo_prestacao && (
            <div className={sol.prazo_prestacao < hojeISO() ? ui.aviso : ui.info} style={{ marginTop: 16 }}>
              Aguardando a prestação de contas do colaborador — prazo: até{' '}
              {formatarData(sol.prazo_prestacao)}
              {sol.prazo_prestacao < hojeISO() && ' (vencido)'}.
            </div>
          )}
        {['em_conferencia', 'prestacao_em_conferencia', 'devolucao_em_conferencia'].includes(sol.status) &&
          sol.solicitante_email === usuarioEmail &&
          tem('financeiro') && (
            <div className={ui.info} style={{ marginTop: 16 }}>
              Este pedido é seu: outra pessoa do financeiro faz a conferência.
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
          <h2 className={ui.subtitulo}>{textoDecisao.titulo}</h2>
          <p className={ui.muted} style={{ marginBottom: 12 }}>
            {textoDecisao.texto}
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
              {textoDecisao.ok}
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
          <h2 className={ui.subtitulo}>
            {sol.status === 'diferenca_aguardando_pagamento'
              ? `Pagar a diferença (${formatarMoeda(-(saldo ?? 0))})`
              : adiantamento
                ? 'Pagar o adiantamento'
                : 'Registrar pagamento'}
          </h2>
          {adiantamento && sol.status === 'aguardando_pagamento' && (
            <p className={ui.muted} style={{ marginBottom: 12 }}>
              {sol.pula_gestor ? 'Pedido de gestor (sem aprovação). ' : 'Aprovado pelo gestor. '}
              Sem nota por enquanto: a conferência é na prestação de contas, depois da viagem.
            </p>
          )}
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
              {sol.status === 'diferenca_aguardando_pagamento'
                ? 'Marcar diferença como paga'
                : adiantamento
                  ? 'Marcar adiantamento como pago'
                  : 'Marcar como paga'}
            </button>
          </div>
          {erroAcao && <div className={ui.erro} style={{ marginTop: 12 }}>{erroAcao}</div>}
        </section>
      )}

      {sol.acoes.includes('enviar_comprovante') && (
        <section className={`${ui.card} ${styles.acoes}`}>
          <h2 className={ui.subtitulo}>Devolver a sobra ({formatarMoeda(saldo ?? 0)})</h2>
          {sol.motivo_devolucao && (
            <div className={ui.aviso} style={{ marginBottom: 12 }}>
              <strong>Comprovante recusado por {sol.devolvido_por}:</strong> {sol.motivo_devolucao}
            </div>
          )}
          <p className={ui.muted} style={{ marginBottom: 12 }}>
            Faça a transferência para a conta que o financeiro passar e anexe o comprovante.
          </p>
          <form className={ui.form} onSubmit={enviarComprovante}>
            <div className={ui.grade}>
              <div className={ui.campo}>
                <label htmlFor="dataTransferencia">Data da transferência</label>
                <input
                  id="dataTransferencia"
                  type="date"
                  value={dataTransferencia}
                  max={hojeISO()}
                  onChange={(e) => setDataTransferencia(e.target.value)}
                  required
                />
              </div>
              <div className={ui.campo}>
                <label htmlFor="comprovante">Comprovante (JPG, PNG ou PDF)</label>
                <input
                  id="comprovante"
                  type="file"
                  accept="image/jpeg,image/png,application/pdf"
                  onChange={(e) => setComprovante(e.target.files?.[0] ?? null)}
                />
              </div>
            </div>
            {erroAcao && <div className={ui.erro}>{erroAcao}</div>}
            <div className={ui.botoes}>
              <button className={ui.botao} disabled={processando}>
                Enviar comprovante
              </button>
            </div>
          </form>
        </section>
      )}

      {sol.acoes.includes('confirmar_devolucao') && (
        <section className={`${ui.card} ${styles.acoes}`}>
          <h2 className={ui.subtitulo}>Confirmar a devolução ({formatarMoeda(saldo ?? 0)})</h2>
          <p className={ui.muted} style={{ marginBottom: 12 }}>
            Confira se o valor caiu na conta. Ao confirmar, o adiantamento é encerrado.
            {comprovanteEnviado && (
              <>
                {' '}
                Transferência em {formatarData(comprovanteEnviado.data_despesa)}.{' '}
                <button
                  type="button"
                  className={styles.link}
                  onClick={() => setNotaAberta(comprovanteEnviado.id)}
                >
                  Ver comprovante
                </button>
              </>
            )}
          </p>
          <div className={ui.campo}>
            <label htmlFor="comentarioDevolucao">Comentário (obrigatório para recusar)</label>
            <textarea
              id="comentarioDevolucao"
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
              onClick={() => agir('confirmar-devolucao', { aprovar: true, comentario: comentario || null })}
            >
              Recebido — encerrar
            </button>
            <button
              className={`${ui.botao} ${ui.perigo}`}
              disabled={processando || !comentario.trim()}
              onClick={() => agir('confirmar-devolucao', { aprovar: false, comentario })}
            >
              Recusar comprovante
            </button>
          </div>
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
            {variasNotas ? (
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
                {adiantamento && (
                  <div>
                    <dt>Diárias</dt>
                    <dd>
                      {sol.diarias} × {formatarMoeda(sol.valor_diaria ?? 0)}
                      {sol.valor_complementar !== null && (
                        <> + complementar {formatarMoeda(sol.valor_complementar)}</>
                      )}{' '}
                      = {formatarMoeda(sol.valor_total)}
                    </dd>
                  </div>
                )}
                {adiantamento && sol.valor_gasto !== null && (
                  <>
                    <div>
                      <dt>Gasto comprovado</dt>
                      <dd>{formatarMoeda(sol.valor_gasto)}</dd>
                    </div>
                    <div>
                      <dt>{saldo !== null && saldo < 0 ? 'Diferença a receber' : 'Sobra a devolver'}</dt>
                      <dd>{formatarMoeda(Math.abs(saldo ?? 0))}</dd>
                    </div>
                  </>
                )}
              </>
            ) : (
              <>
                <div>
                  <dt>Data da despesa</dt>
                  <dd>{formatarData(sol.despesas[0]?.data_despesa ?? null)}</dd>
                </div>
                {sol.motivo && (
                  <div>
                    <dt>Motivo</dt>
                    <dd>{sol.motivo}</dd>
                  </div>
                )}
                {sol.local_refeicao_rotulo && (
                  <div>
                    <dt>Local da refeição</dt>
                    <dd>{sol.local_refeicao_rotulo}</dd>
                  </div>
                )}
              </>
            )}
            {sol.data_pagamento && (
              <div>
                <dt>{adiantamento ? 'Adiantamento pago em' : 'Pago em'}</dt>
                <dd>{formatarData(sol.data_pagamento)}</dd>
              </div>
            )}
            {sol.data_pagamento_diferenca && (
              <div>
                <dt>Diferença paga em</dt>
                <dd>{formatarData(sol.data_pagamento_diferenca)}</dd>
              </div>
            )}
            <div style={{ gridColumn: '1 / -1' }}>
              <dt>{variasNotas ? 'Motivo da viagem' : 'Descrição'}</dt>
              <dd>{sol.descricao}</dd>
            </div>
          </dl>
        </section>

        {sol.despesas.length > 0 && (
          <section className={ui.card}>
            <h2 className={ui.subtitulo}>
              {despesa?.categoria === 'comprovante_devolucao' ? 'Comprovante' : 'Nota'}
            </h2>
            {variasNotas && !despesa && <p className={ui.muted}>Escolha uma nota na lista abaixo.</p>}
            {variasNotas && despesa && (
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
        )}
      </div>

      {variasNotas && sol.despesas.length > 0 && (
        <section className={ui.card}>
          <h2 className={ui.subtitulo}>
            {adiantamento ? 'Notas da prestação de contas' : 'Notas'} ({notas.length})
          </h2>
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

/** "sobra de R$ X (o colaborador devolve)" etc., a partir do saldo da API. */
function resumoSaldo(saldo: number | null, passado = false): string {
  if (saldo === null) return ''
  if (saldo > 0)
    return passado
      ? `Sobraram ${formatarMoeda(saldo)}, devolvidos pelo colaborador.`
      : `sobra de ${formatarMoeda(saldo)} (o colaborador devolve).`
  if (saldo < 0)
    return passado
      ? `Gasto ${formatarMoeda(-saldo)} acima do adiantado, reembolsado ao colaborador.`
      : `gasto ${formatarMoeda(-saldo)} acima do adiantado (diferença a reembolsar).`
  return passado ? 'O gasto bateu com o adiantamento.' : 'o gasto bate com o adiantamento.'
}
