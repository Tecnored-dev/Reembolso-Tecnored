import { useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useContexto } from '@/components/contexto'
import { api } from '@/services/api'
import ui from '@/styles/ui.module.css'
import { caminhoInterno, mensagemErro } from '@/utils'

// Matrícula: informada uma vez (1º acesso) e copiada em cada solicitação. O
// centro de custo saiu do perfil e é escolhido em cada pedido (Thais, 15/10).
export default function PerfilPage() {
  const { perfil, recarregarPerfil } = useContexto()
  const [matricula, setMatricula] = useState(perfil.matricula ?? '')
  const [erro, setErro] = useState<string | null>(null)
  const [salvando, setSalvando] = useState(false)
  const [salvo, setSalvo] = useState(false)
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const voltar = caminhoInterno(params.get('voltar'))
  const primeiroAcesso = !perfil.completo

  async function salvar(e: FormEvent) {
    e.preventDefault()
    setErro(null)
    setSalvo(false)
    setSalvando(true)
    try {
      await api.put('/api/perfil', { matricula })
      await recarregarPerfil()
      if (primeiroAcesso) navigate(voltar, { replace: true })
      else setSalvo(true)
    } catch (err) {
      setErro(mensagemErro(err))
    } finally {
      setSalvando(false)
    }
  }

  return (
    <section className={ui.card}>
      <h1 className={ui.titulo}>{primeiroAcesso ? 'Bem-vindo! Complete seu cadastro' : 'Meu perfil'}</h1>
      <p className={ui.muted} style={{ marginBottom: 18 }}>
        {primeiroAcesso
          ? 'Só desta vez: sua matrícula vai automaticamente em todas as suas solicitações.'
          : `${perfil.nome} · ${perfil.email}`}
      </p>

      <form className={ui.form} onSubmit={salvar}>
        <div className={ui.campo}>
          <label htmlFor="matricula">Matrícula</label>
          <input
            id="matricula"
            value={matricula}
            onChange={(e) => setMatricula(e.target.value)}
            maxLength={30}
            required
          />
          <span className={ui.ajuda}>O centro de custo você escolhe em cada pedido.</span>
        </div>

        {erro && <div className={ui.erro}>{erro}</div>}
        {salvo && <div className={ui.info}>Perfil atualizado.</div>}

        <div className={`${ui.botoes} ${ui.barraAcao}`}>
          <button className={ui.botao} disabled={salvando || !matricula.trim()}>
            {salvando ? 'Salvando…' : primeiroAcesso ? 'Continuar' : 'Salvar'}
          </button>
        </div>
      </form>
    </section>
  )
}
