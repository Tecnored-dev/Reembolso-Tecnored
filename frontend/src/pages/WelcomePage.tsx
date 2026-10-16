import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, DEV_LOGIN_URL, LOGIN_URL } from '@/services/api'
import type { AppConfig, Session } from '@/types'
import { formatVersion } from '@/utils'
import styles from './WelcomePage.module.css'

const SSO_COUNTDOWN_SECONDS = 3

export default function WelcomePage() {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const authError = searchParams.get('auth_error')

  // Contador da telinha "Login SSO via Cloudflare..." — null = não mostra.
  // Só aparece na primeira entrada via SSO do Cloudflare Access nesta aba
  // (sessionStorage), não a cada reabertura (seção 17.1 do README do Hello-World).
  const [ssoCountdown, setSsoCountdown] = useState<number | null>(null)

  // Carrega os textos/cores configuráveis do backend
  useEffect(() => {
    api.get<AppConfig>('/api/config').then((res) => setConfig(res.data))
  }, [])

  // Sessão válida (ou recém-criada pelo SSO do Cloudflare Access): vai direto
  // para o início — no SSO, mostra antes a telinha de transição.
  useEffect(() => {
    api
      .get<Session>('/api/session')
      .then((res) => {
        if (res.data.login_method === 'cloudflare' && !sessionStorage.getItem('sso-visto')) {
          sessionStorage.setItem('sso-visto', '1')
          setSsoCountdown(SSO_COUNTDOWN_SECONDS)
        } else {
          navigate('/inicio', { replace: true })
        }
      })
      .catch(() => {
        // 401 = sem sessão, permanece na tela de boas-vindas
      })
  }, [navigate])

  // Conta regressiva de 1 em 1 segundo até navegar para o início
  useEffect(() => {
    if (ssoCountdown === null) return
    if (ssoCountdown === 0) {
      navigate('/inicio', { replace: true })
      return
    }
    const timer = setTimeout(() => setSsoCountdown((c) => (c ?? 1) - 1), 1000)
    return () => clearTimeout(timer)
  }, [ssoCountdown, navigate])

  const bgColor = config?.bg_color ?? '#32746a'

  return (
    <div className={styles.page} style={{ background: bgColor }}>
      <div className={styles.card}>
        <img src="/tecnored-logo.png" alt="Tecnored" className={styles.logo} />

        <h1 className={styles.title}>{config?.title ?? 'Reembolso'}</h1>

        <p className={styles.welcomeMsg}>
          {config?.welcome_msg ?? 'Reembolso de alimentação e viagem'}
        </p>

        {ssoCountdown !== null ? (
          // Login SSO via Cloudflare Access já concluído (seção 17.1) — só
          // dá tempo do usuário entender o que aconteceu antes de navegar,
          // em vez de um flash quase imperceptível para o /inicio.
          <div className={styles.ssoTransition} aria-live="polite">
            <div className={styles.ssoSpinner} />
            <p className={styles.ssoMessage}>Login SSO via Cloudflare…</p>
            <p className={styles.ssoCount}>{ssoCountdown}</p>
          </div>
        ) : (
          <>
            {authError && (
              <p className={styles.errorNote} role="alert">
                Não foi possível concluir o login ({authError}). Tente novamente.
              </p>
            )}

            {/* Navegação de página inteira — obrigatório para o fluxo OAuth */}
            <a href={LOGIN_URL} className={styles.btnMicrosoft}>
              <svg className={styles.msIcon} viewBox="0 0 21 21" xmlns="http://www.w3.org/2000/svg">
                <rect x="1" y="1" width="9" height="9" fill="#f25022" />
                <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
                <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
                <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
              </svg>
              Entrar com Microsoft
            </a>

            {config?.login_dev && (
              // Só aparece em APP_ENV=local com DEV_LOGIN_ENABLED (antes do
              // App Registration existir). A API se recusa a subir assim em hml/main.
              <a href={DEV_LOGIN_URL} className={styles.btnDev}>
                Entrar como dev (local)
              </a>
            )}

            <p className={styles.footerNote}>
              Use sua conta corporativa <strong>@tecnored.com.br</strong>.
              <br />
              O login é gerenciado pela Microsoft — suas credenciais não passam por esta aplicação.
            </p>
          </>
        )}
      </div>

      <footer className={styles.pageFooter}>
        Tecnored &mdash; Reembolso
        {formatVersion(config) && <> &mdash; {formatVersion(config)}</>}
      </footer>
    </div>
  )
}
