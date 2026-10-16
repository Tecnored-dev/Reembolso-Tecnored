import { Link, useNavigate } from 'react-router-dom'
import StatusBadge from '@/components/StatusBadge'
import { useApi } from '@/hooks/useApi'
import ui from '@/styles/ui.module.css'
import type { SolicitacaoResumo } from '@/types'
import { formatarDataHora, formatarMoeda } from '@/utils'

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
  const { data, loading, error } = useApi<SolicitacaoResumo[]>(
    `/api/solicitacoes?escopo=${escopo}`
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
        <div style={{ overflowX: 'auto' }}>
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
                      <span title={s.alerta_limite} aria-label="Acima do limite">
                        {' '}
                        ⚠️
                      </span>
                    )}
                  </td>
                  <td className={ui.direita}>{formatarMoeda(s.valor_total, s.moeda)}</td>
                  <td>
                    <StatusBadge status={s.status} titulo={s.status_rotulo} />
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
    </section>
  )
}
