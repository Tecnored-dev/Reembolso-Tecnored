import { useCallback, useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import type { Contexto } from '@/components/contexto'
import Icone from '@/components/Icone'
import { api, LOGOUT_URL } from '@/services/api'
import type { AppConfig, Perfil, Session, SolicitacaoResumo } from '@/types'
import { formatVersion } from '@/utils'
import styles from './Layout.module.css'

// "Colaborador Teste" → "CT": aparece no lugar do nome no celular.
function iniciais(nome: string) {
  const partes = nome.trim().split(/\s+/).filter(Boolean)
  if (partes.length === 0) return '?'
  const primeira = partes[0][0]
  const ultima = partes.length > 1 ? partes[partes.length - 1][0] : ''
  return (primeira + ultima).toUpperCase()
}

// Moldura das telas autenticadas: cabeçalho, menu por papel e rodapé.
// Sem sessão → volta para a tela de entrada. O perfil (matrícula e centro de
// custo) só é exigido para PEDIR reembolso — gestor e financeiro conseguem
// aprovar/pagar sem preencher nada.
export default function Layout() {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [session, setSession] = useState<Session | null>(null)
  const [perfil, setPerfil] = useState<Perfil | null>(null)
  const [contadores, setContadores] = useState<Record<string, number>>({})
  const navigate = useNavigate()
  const { pathname } = useLocation()

  const recarregarPerfil = useCallback(async () => {
    const res = await api.get<Perfil>('/api/perfil')
    setPerfil(res.data)
  }, [])

  useEffect(() => {
    api.get<AppConfig>('/api/config').then((res) => setConfig(res.data))
    api
      .get<Session>('/api/session')
      .then((res) => {
        setSession(res.data)
        return recarregarPerfil()
      })
      .catch(() => navigate('/', { replace: true })) // 401 — sem sessão
  }, [navigate, recarregarPerfil])

  // Tamanho das filas que a pessoa trabalha (contador no menu). Busca de novo a
  // cada troca de tela, para o número cair depois de conferir, aprovar ou pagar.
  useEffect(() => {
    if (!session) return
    const escopos = [
      session.papeis.includes('financeiro') && 'conferencia',
      session.papeis.includes('gestor') && 'aprovacao',
      session.papeis.includes('financeiro') && 'pagamento',
    ].filter((e): e is string => !!e)
    escopos.forEach((escopo) => {
      api
        .get<SolicitacaoResumo[]>(`/api/solicitacoes?escopo=${escopo}`)
        .then((res) => setContadores((atual) => ({ ...atual, [escopo]: res.data.length })))
        .catch(() => undefined) // sem contador: o menu continua funcionando
    })
  }, [session, pathname])

  if (!session || !config || !perfil) return <div className={styles.carregando}>Carregando…</div>

  const tem = (papel: Session['papeis'][number]) => session.papeis.includes(papel)
  const menu = [
    { para: '/inicio', rotulo: 'Meus reembolsos', mostrar: true },
    { para: '/conferencia', rotulo: 'Conferência', mostrar: tem('financeiro'), fila: 'conferencia' },
    { para: '/aprovacoes', rotulo: 'Aprovações', mostrar: tem('gestor'), fila: 'aprovacao' },
    { para: '/pagamentos', rotulo: 'Pagamentos', mostrar: tem('financeiro'), fila: 'pagamento' },
    { para: '/todas', rotulo: 'Todas', mostrar: tem('financeiro') || tem('admin') },
  ].filter((item) => item.mostrar)

  const contexto: Contexto = { session, config, perfil, recarregarPerfil, tem }

  return (
    <div className={styles.page}>
      <header className={styles.header} style={{ background: config.bg_color }}>
        <div className={styles.marca}>
          <img src="/tecnored-logo-branca.png" alt="Tecnored" className={styles.logo} />
          <span className={styles.sep} aria-hidden="true" />
          {config.title}
        </div>
        <div className={styles.usuario}>
          {config.env !== 'main' && <span className={styles.ambiente}>{config.env}</span>}
          <NavLink to="/perfil" className={styles.nomeUsuario} title="Meu perfil">
            <span className={styles.avatar} aria-hidden="true">
              {iniciais(session.name)}
            </span>
            <span className={styles.nome}>{session.name}</span>
          </NavLink>
          <a href={LOGOUT_URL} className={styles.sair}>
            <Icone nome="sair" tamanho={18} />
            Sair
          </a>
        </div>
      </header>

      <nav className={styles.menu} aria-label="Menu principal">
        {menu.map((item) => (
          <NavLink
            key={item.para}
            to={item.para}
            className={({ isActive }) => (isActive ? `${styles.item} ${styles.ativo}` : styles.item)}
          >
            {item.rotulo}
            {item.fila && contadores[item.fila] > 0 && (
              <span
                className={styles.contador}
                aria-label={`${contadores[item.fila]} ${contadores[item.fila] === 1 ? 'pedido' : 'pedidos'} na fila`}
              >
                {contadores[item.fila]}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <main className={styles.conteudo}>
        <Outlet context={contexto} />
      </main>

      <footer className={styles.rodape}>
        Tecnored &mdash; Reembolso
        {formatVersion(config) && <> &mdash; {formatVersion(config)}</>}
      </footer>
    </div>
  )
}
