import { useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Icone, { type NomeIcone } from '@/components/Icone'
import StatusBadge from '@/components/StatusBadge'
import { useApi } from '@/hooks/useApi'
import { comQuemEsta, VISUAL } from '@/statusVisual'
import ui from '@/styles/ui.module.css'
import type { SolicitacaoResumo, TipoSolicitacao } from '@/types'
import { formatarDataHora, formatarMoeda } from '@/utils'
import styles from './ListaPage.module.css'

const ICONE_TIPO: Record<TipoSolicitacao, NomeIcone> = {
  alimentacao: 'talher',
  diversas: 'caixa',
  viagem: 'mala',
  adiantamento: 'carteira',
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

      {data && data.length === 0 && <div className={ui.vazio}>{vazio}</div>}

      {data && data.length > 0 && (
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
              {data.map((s) => (
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
                    {escopo === 'minhas' && (
                      <div className={styles.quemTabela}>{comQuemEsta(s.status, s.gestor_nome).quem}</div>
                    )}
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

      {data && data.length > 0 && (
        <div className={styles.cartoes}>
          {data.map((s) => {
            const quem = comQuemEsta(s.status, s.gestor_nome)
            const precisa = escopo === 'minhas' && VISUAL[s.status]?.familia === 'voce'
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
                  {escopo === 'minhas' && (
                    <span className={styles.comQuem}>
                      <strong>{quem.quem}.</strong> {quem.frase}
                    </span>
                  )}
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
