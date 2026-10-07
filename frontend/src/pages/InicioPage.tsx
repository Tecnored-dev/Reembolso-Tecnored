import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, LOGOUT_URL } from '@/services/api'
import type { AppConfig, Session } from '@/types'
import { formatVersion, rotuloPapel } from '@/utils'
import styles from './InicioPage.module.css'

// Tela inicial autenticada. Por enquanto mostra quem está logado e com quais
// papéis — as telas do reembolso (Meus reembolsos, Aprovações, Financeiro)
// entram a partir daqui.
export default function InicioPage() {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [session, setSession] = useState<Session | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    api.get<AppConfig>('/api/config').then((res) => setConfig(res.data))
    api
      .get<Session>('/api/session')
      .then((res) => setSession(res.data))
      .catch(() => navigate('/', { replace: true })) // 401 — sem sessão
  }, [navigate])

  if (!session || !config) return null

  return (
    <div className={styles.page}>
      <header className={styles.header} style={{ background: config.bg_color }}>
        <h1>{config.title} · Tecnored</h1>
        <div className={styles.userInfo}>
          <span>{session.name}</span>
          <span className={styles.envBadge}>{config.env}</span>
          <a href={LOGOUT_URL} className={styles.btnLogout}>
            Sair
          </a>
        </div>
      </header>

      <main className={styles.content}>
        <section className={styles.card}>
          <h2>Olá, {session.name.split(' ')[0]}!</h2>
          <p className={styles.muted}>{session.email}</p>
          <div className={styles.papeis} aria-label="Seus papéis">
            {session.papeis.map((p) => (
              <span key={p} className={styles.papel}>
                {rotuloPapel(p)}
              </span>
            ))}
          </div>
        </section>

        <section className={styles.card}>
          <h2>Em construção</h2>
          <p className={styles.muted}>
            Aqui vão entrar os seus pedidos de reembolso e, para gestores e financeiro, as filas
            de aprovação e pagamento.
          </p>
        </section>
      </main>

      <footer className={styles.pageFooter}>
        Tecnored &mdash; Reembolso
        {formatVersion(config) && <> &mdash; {formatVersion(config)}</>}
      </footer>
    </div>
  )
}
