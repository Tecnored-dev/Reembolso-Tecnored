import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Icone, { type NomeIcone } from '@/components/Icone'
import StatusBadge from '@/components/StatusBadge'
import { useApi } from '@/hooks/useApi'
import { comQuemEsta, CURTO, VISUAL } from '@/statusVisual'
import ui from '@/styles/ui.module.css'
import { DIAS_ALERTA, diasDesde, emAndamento, textoParado } from '@/tempo'
import type { SolicitacaoResumo, TipoSolicitacao } from '@/types'
import { formatarDataHora, formatarMoeda } from '@/utils'
import styles from './ListaPage.module.css'

const ICONE_TIPO: Record<TipoSolicitacao, NomeIcone> = {
  alimentacao: 'talher',
  diversas: 'caixa',
  viagem: 'mala',
  adiantamento: 'carteira',
}

type Filtro = 'todos' | 'voce' | 'andamento' | 'finalizados'

const FILTROS: { id: Filtro; rotulo: string }[] = [
  { id: 'todos', rotulo: 'Todos' },
  { id: 'voce', rotulo: 'Com você' },
  { id: 'andamento', rotulo: 'Em andamento' },
  { id: 'finalizados', rotulo: 'Finalizados' },
]

function comVoce(s: SolicitacaoResumo): boolean {
  return VISUAL[s.status]?.familia === 'voce'
}

function noFiltro(s: SolicitacaoResumo, filtro: Filtro): boolean {
  if (filtro === 'voce') return comVoce(s)
  if (filtro === 'andamento') return emAndamento(s.status)
  if (filtro === 'finalizados') return !emAndamento(s.status)
  return true
}

// "Parado há 3 dias": só para pedido que ainda está andando. A partir de
// DIAS_ALERTA dias fica em âmbar, para quem espera perceber que passou do normal.
function Parado({ s, className }: { s: SolicitacaoResumo; className: string }) {
  if (!emAndamento(s.status)) return null
  const dias = diasDesde(s.ultima_movimentacao_em)
  return (
    <span
      className={dias >= DIAS_ALERTA ? `${className} ${styles.paradoAlerta}` : className}
      title="Tempo desde a última movimentação"
    >
      <Icone nome="relogio" tamanho={14} />
      {textoParado(dias)}
    </span>
  )
}

export type Escopo = 'minhas' | 'conferencia' | 'aprovacao' | 'pagamento' | 'todas'

interface Props {
  escopo: Escopo
  titulo: string
  descricao: string
  vazio: string
}

// Uma tela de lista serve para tudo: meus pedidos, as filas do financeiro e
// do gestor, e a visão geral. Muda só o "escopo" pedido à API.
export default function ListaPage({ escopo, titulo, descricao, vazio }: Props) {
  const { data: recebidos, loading, error } = useApi<SolicitacaoResumo[]>(
    `/api/solicitacoes?escopo=${escopo}`
  )
  // Nas filas de trabalho, o pedido parado há mais tempo vem primeiro.
  const fila = escopo === 'conferencia' || escopo === 'aprovacao' || escopo === 'pagamento'
  const data = useMemo(
    () =>
      recebidos && fila
        ? [...recebidos].sort((a, b) => a.ultima_movimentacao_em.localeCompare(b.ultima_movimentacao_em))
        : recebidos,
    [recebidos, fila]
  )
  const navigate = useNavigate()
  const mostrarSolicitante = escopo !== 'minhas'
  const minhas = escopo === 'minhas'

  const [filtro, setFiltro] = useState<Filtro>('todos')
  const [busca, setBusca] = useState('')
  // Pedidos que estão com o colaborador (devolvidos, prestar contas, devolver sobra).
  const precisam = useMemo(() => (minhas && data ? data.filter(comVoce) : []), [minhas, data])
  const contagem = useMemo(
    () => Object.fromEntries(FILTROS.map((f) => [f.id, (data ?? []).filter((s) => noFiltro(s, f.id)).length])),
    [data]
  )
  const termo = busca.trim().toLowerCase()
  const visiveis = useMemo(() => {
    if (!data || !minhas) return data
    return data.filter(
      (s) =>
        noFiltro(s, filtro) &&
        (!termo || `${s.codigo} ${s.destino ?? ''} ${s.descricao} ${s.tipo_rotulo} ${CURTO[s.status]}`.toLowerCase().includes(termo))
    )
  }, [data, minhas, filtro, termo])

  return (
    <section className={ui.card}>
      <div className={ui.cabecalho}>
        <div>
          <h1 className={ui.titulo}>{titulo}</h1>
          <p className={ui.muted}>{descricao}</p>
        </div>
        {escopo === 'minhas' && (
          <div className={ui.botoes}>
            <Link to="/nova" className={ui.botao}>
              + Reembolso de despesas
            </Link>
            <Link to="/nova/viagem" className={ui.botao}>
              + Diária de Viagem
            </Link>
            <Link to="/nova/adiantamento" className={ui.botao}>
              + Adiantamento
            </Link>
          </div>
        )}
      </div>

      {loading && <p className={ui.muted}>Carregando…</p>}
      {error && <div className={ui.erro}>{error}</div>}

      {precisam.length > 0 && (
        <div className={styles.acao} role="region" aria-label="Precisa da sua ação">
          <h2 className={styles.acaoTitulo}>
            <Icone nome="alerta" tamanho={20} />
            Precisa da sua ação ({precisam.length})
          </h2>
          <ul className={styles.acaoLista}>
            {precisam.map((s) => (
              <li key={s.id} className={styles.acaoItem}>
                <div className={styles.acaoTexto}>
                  <strong>{s.destino ? `${s.destino} · ${s.descricao}` : s.descricao}</strong>
                  <span>
                    {s.codigo} · {comQuemEsta(s.status, s.gestor_nome).frase}
                  </span>
                </div>
                <Link to={`/solicitacoes/${s.id}`} className={`${ui.botao} ${ui.secundario}`}>
                  Abrir pedido
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      {minhas && data && data.length > 1 && (
        <div className={styles.filtros}>
          <div className={styles.chips} role="group" aria-label="Filtrar pedidos">
            {FILTROS.map((f) => (
              <button
                key={f.id}
                type="button"
                className={filtro === f.id ? `${styles.chip} ${styles.chipAtivo}` : styles.chip}
                aria-pressed={filtro === f.id}
                onClick={() => setFiltro(f.id)}
              >
                {f.rotulo} <span className={styles.chipNum}>{contagem[f.id]}</span>
              </button>
            ))}
          </div>
          <div className={`${ui.campo} ${styles.busca}`}>
            <label htmlFor="busca">Buscar pedido</label>
            <input
              id="busca"
              type="search"
              value={busca}
              placeholder="Código, destino ou descrição"
              onChange={(e) => setBusca(e.target.value)}
            />
          </div>
        </div>
      )}

      {data && data.length === 0 && <div className={ui.vazio}>{vazio}</div>}

      {data && data.length > 0 && visiveis && visiveis.length === 0 && (
        <div className={ui.vazio}>Nenhum pedido encontrado com esse filtro.</div>
      )}

      {visiveis && visiveis.length > 0 && (
        <div className={styles.tabelaWrap} style={{ overflowX: 'auto' }}>
          <table className={ui.tabela}>
            <thead>
              <tr>
                <th>Código</th>
                {mostrarSolicitante && <th>Solicitante</th>}
                <th>Tipo</th>
                <th className={ui.opcional}>Descrição</th>
                <th className={ui.direita}>Valor</th>
                <th>Status</th>
                <th className={ui.opcional}>Última movimentação</th>
              </tr>
            </thead>
            <tbody>
              {visiveis.map((s) => (
                <tr key={s.id} onClick={() => navigate(`/solicitacoes/${s.id}`)}>
                  <td className={ui.codigo}>
                    <Link to={`/solicitacoes/${s.id}`} onClick={(e) => e.stopPropagation()}>
                      {s.codigo}
                    </Link>
                  </td>
                  {mostrarSolicitante && (
                    <td>
                      {s.solicitante_nome}
                      {s.criado_por_nome && (
                        <div className={ui.muted}>pedido por {s.criado_por_nome}</div>
                      )}
                    </td>
                  )}
                  <td>{s.tipo_rotulo}</td>
                  <td className={ui.opcional}>
                    {s.destino ? `${s.destino} · ${s.descricao}` : s.descricao}
                    {escopo === 'minhas' && s.criado_por_nome && (
                      <div className={ui.muted}>
                        {s.criado_por_email === s.solicitante_email
                          ? ''
                          : `${s.solicitante_nome} · pedido por ${s.criado_por_nome}`}
                      </div>
                    )}
                    {s.alerta_limite && (
                      <span className={styles.alerta} title={s.alerta_limite} role="img" aria-label="Acima do limite">
                        {' '}
                        <Icone nome="alerta" tamanho={16} />
                      </span>
                    )}
                  </td>
                  <td className={ui.direita}>{formatarMoeda(s.valor_total, s.moeda)}</td>
                  <td>
                    <StatusBadge status={s.status} titulo={s.status_rotulo} />
                    <div className={styles.quemTabela}>
                      {minhas && <>{comQuemEsta(s.status, s.gestor_nome).quem} </>}
                      <Parado s={s} className={styles.parado} />
                    </div>
                  </td>
                  <td className={`${ui.muted} ${ui.opcional}`}>
                    {formatarDataHora(s.ultima_movimentacao_em)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {visiveis && visiveis.length > 0 && (
        <div className={styles.cartoes}>
          {visiveis.map((s) => {
            const quem = comQuemEsta(s.status, s.gestor_nome)
            const precisa = minhas && comVoce(s)
            return (
              <Link
                key={s.id}
                to={`/solicitacoes/${s.id}`}
                className={precisa ? `${styles.pedido} ${styles.precisa}` : styles.pedido}
              >
                <span className={styles.tipoIc}>
                  <Icone nome={ICONE_TIPO[s.tipo] ?? 'recibo'} tamanho={22} />
                </span>
                <span className={styles.desc}>{s.destino ? `${s.destino} · ${s.descricao}` : s.descricao}</span>
                <span className={styles.valor}>{formatarMoeda(s.valor_total, s.moeda)}</span>
                <span className={styles.meta}>
                  {s.codigo} · {s.tipo_rotulo}
                  {mostrarSolicitante && <> · {s.solicitante_nome}</>} · {formatarDataHora(s.ultima_movimentacao_em)}
                </span>
                <span className={styles.estado}>
                  <StatusBadge status={s.status} titulo={s.status_rotulo} />
                  {minhas && (
                    <span className={styles.comQuem}>
                      <strong>{quem.quem}.</strong> {quem.frase}
                    </span>
                  )}
                  <Parado s={s} className={styles.parado} />
                  {s.alerta_limite && (
                    <span className={styles.alerta} title={s.alerta_limite} role="img" aria-label="Acima do limite">
                      <Icone nome="alerta" tamanho={16} />
                    </span>
                  )}
                </span>
              </Link>
            )
          })}
        </div>
      )}
    </section>
  )
}
