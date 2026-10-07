import { useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useContexto } from '@/components/contexto'
import { useApi } from '@/hooks/useApi'
import { api } from '@/services/api'
import ui from '@/styles/ui.module.css'
import type { Cadastros } from '@/types'
import { caminhoInterno, mensagemErro } from '@/utils'

// Matrícula e centro de custo: informados uma vez (1º acesso) e copiados em
// cada solicitação. O centro de custo é sempre o do próprio colaborador.
export default function PerfilPage() {
  const { perfil, recarregarPerfil } = useContexto()
  const { data: cadastros } = useApi<Cadastros>('/api/cadastros')
  const [matricula, setMatricula] = useState(perfil.matricula ?? '')
  const [centro, setCentro] = useState(perfil.centro_custo?.id.toString() ?? '')
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
      await api.put('/api/perfil', { matricula, centro_custo_id: Number(centro) })
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
          ? 'Só desta vez: esses dados vão automaticamente em todas as suas solicitações.'
          : `${perfil.nome} · ${perfil.email}`}
      </p>

      <form className={ui.form} onSubmit={salvar}>
        <div className={ui.grade}>
          <div className={ui.campo}>
            <label htmlFor="matricula">Matrícula</label>
            <input
              id="matricula"
              value={matricula}
              onChange={(e) => setMatricula(e.target.value)}
              maxLength={30}
              required
            />
          </div>
          <div className={ui.campo}>
            <label htmlFor="centro">Centro de custo da sua matrícula</label>
            <select id="centro" value={centro} onChange={(e) => setCentro(e.target.value)} required>
              <option value="">Selecione…</option>
              {cadastros?.centros_custo.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.rotulo}
                </option>
              ))}
            </select>
          </div>
        </div>

        {erro && <div className={ui.erro}>{erro}</div>}
        {salvo && <div className={ui.info}>Perfil atualizado.</div>}

        <div className={ui.botoes}>
          <button className={ui.botao} disabled={salvando || !matricula.trim() || !centro}>
            {salvando ? 'Salvando…' : primeiroAcesso ? 'Continuar' : 'Salvar'}
          </button>
        </div>
      </form>
    </section>
  )
}
