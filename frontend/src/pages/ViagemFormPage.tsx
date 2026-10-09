import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { useContexto } from '@/components/contexto'
import NotasViagem from '@/components/NotasViagem'
import { useApi } from '@/hooks/useApi'
import { anexarNotas, conferirNotas, novaNota, notasEnviadas, type NotaForm } from '@/notas'
import { api } from '@/services/api'
import ui from '@/styles/ui.module.css'
import type { Cadastros, Gestor, Solicitacao } from '@/types'
import { mensagemErro } from '@/utils'

// Reembolso de viagem (o colaborador pagou e pede depois, com as notas), ou a
// correção de um devolvido (/solicitacoes/:id/corrigir-viagem). Mesmo fluxo da
// alimentação; a diferença é aceitar várias notas, cada uma com categoria.
export default function ViagemFormPage() {
  const { id } = useParams()
  const corrigindo = Boolean(id)
  const { tem, perfil } = useContexto()
  const pulaGestor = tem('gestor')
  const navigate = useNavigate()

  const { data: cadastros } = useApi<Cadastros>('/api/cadastros')
  const [gestores, setGestores] = useState<Gestor[]>([])
  const [gestoresCarregados, setGestoresCarregados] = useState(false)
  const [original, setOriginal] = useState<Solicitacao | null>(null)

  const [destino, setDestino] = useState('')
  const [inicio, setInicio] = useState('')
  const [fim, setFim] = useState('')
  const [descricao, setDescricao] = useState('')
  const [empresa, setEmpresa] = useState('')
  const [gestor, setGestor] = useState('')
  const [notas, setNotas] = useState<NotaForm[]>(() => [novaNota()])
  const [erro, setErro] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    if (!pulaGestor)
      api.get<Gestor[]>('/api/gestores').then((r) => {
        setGestores(r.data)
        setGestoresCarregados(true)
      })
  }, [pulaGestor])

  // Correção: carrega o que foi enviado para editar em cima.
  useEffect(() => {
    if (!id || !cadastros) return
    api.get<Solicitacao>(`/api/solicitacoes/${id}`).then((r) => {
      const s = r.data
      setOriginal(s)
      setDestino(s.destino ?? '')
      setInicio(s.viagem_inicio ?? '')
      setFim(s.viagem_fim ?? '')
      setDescricao(s.descricao)
      setEmpresa(String(cadastros.empresas.find((e) => e.nome === s.empresa)?.id ?? ''))
      setGestor(s.gestor_email ?? '')
      setNotas(notasEnviadas(s.despesas))
    })
  }, [id, cadastros])

  async function enviar(e: FormEvent) {
    e.preventDefault()
    setErro(null)
    const problema = conferirNotas(notas)
    if (problema) {
      setErro(problema)
      return
    }

    const form = new FormData()
    anexarNotas(form, notas)
    form.append('destino', destino)
    form.append('viagem_inicio', inicio)
    form.append('viagem_fim', fim)
    form.append('descricao', descricao)
    form.append('empresa_id', empresa)
    if (!pulaGestor) form.append('gestor_email', gestor)

    setEnviando(true)
    try {
      const url = corrigindo ? `/api/solicitacoes/${id}/reenviar-viagem` : '/api/solicitacoes/viagem'
      // multipart explícito: sem isso o axios converteria o FormData em JSON.
      const res = await api.post<Solicitacao>(url, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      navigate(`/solicitacoes/${res.data.id}`, { replace: true, state: { enviado: true } })
    } catch (err) {
      setErro(mensagemErro(err))
    } finally {
      setEnviando(false)
    }
  }

  if (!perfil.completo) return <Navigate to="/perfil?voltar=/nova/viagem" replace />

  if (corrigindo && original && !original.acoes.includes('reenviar')) {
    return (
      <section className={ui.card}>
        <div className={ui.aviso}>Esta solicitação não está aguardando correção.</div>
      </section>
    )
  }

  return (
    <section className={ui.card}>
      <div className={ui.cabecalho}>
        <div>
          <h1 className={ui.titulo}>
            {corrigindo ? `Corrigir ${original?.codigo ?? ''}` : 'Novo reembolso de viagem'}
          </h1>
          <p className={ui.muted}>
            {perfil.matricula} · {perfil.centro_custo?.rotulo}
          </p>
        </div>
      </div>

      {original?.motivo_devolucao && (
        <div className={ui.aviso} style={{ marginBottom: 16 }}>
          <strong>Devolvida por {original.devolvido_por}:</strong> {original.motivo_devolucao}
        </div>
      )}

      <form className={ui.form} onSubmit={enviar}>
        <h2 className={ui.subtitulo}>Viagem</h2>
        <div className={ui.campo}>
          <label htmlFor="destino">Destino</label>
          <input
            id="destino"
            value={destino}
            maxLength={200}
            placeholder="Ex.: Marabá - PA"
            onChange={(e) => setDestino(e.target.value)}
            required
          />
        </div>
        <div className={ui.grade}>
          <div className={ui.campo}>
            <label htmlFor="inicio">Início da viagem</label>
            <input id="inicio" type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} required />
          </div>
          <div className={ui.campo}>
            <label htmlFor="fim">Fim da viagem</label>
            <input
              id="fim"
              type="date"
              value={fim}
              min={inicio || undefined}
              onChange={(e) => setFim(e.target.value)}
              required
            />
          </div>
        </div>
        <div className={ui.campo}>
          <label htmlFor="descricao">Motivo da viagem</label>
          <textarea
            id="descricao"
            value={descricao}
            maxLength={500}
            placeholder="Ex.: Visita técnica à planta de Marabá"
            onChange={(e) => setDescricao(e.target.value)}
            required
          />
          <span className={ui.ajuda}>{descricao.length}/500</span>
        </div>

        <div className={ui.grade}>
          <div className={ui.campo}>
            <label htmlFor="empresa">Empresa de débito</label>
            <select id="empresa" value={empresa} onChange={(e) => setEmpresa(e.target.value)} required>
              <option value="">Selecione…</option>
              {cadastros?.empresas.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.nome}
                </option>
              ))}
            </select>
          </div>
          {!pulaGestor && (
            <div className={ui.campo}>
              <label htmlFor="gestor">Gestor que vai aprovar</label>
              <select id="gestor" value={gestor} onChange={(e) => setGestor(e.target.value)} required>
                <option value="">Selecione…</option>
                {gestores.map((g) => (
                  <option key={g.email} value={g.email}>
                    {g.nome}
                  </option>
                ))}
              </select>
              {gestoresCarregados && gestores.length === 0 && (
                <span className={ui.ajuda}>
                  Nenhum gestor cadastrado ainda. Avise o financeiro para conferir o grupo de
                  gestores.
                </span>
              )}
            </div>
          )}
        </div>
        {pulaGestor && (
          <p className={ui.ajuda}>
            Como você é gestor, depois da conferência do financeiro segue direto para pagamento.
          </p>
        )}

        <h2 className={ui.subtitulo}>Notas</h2>
        <NotasViagem notas={notas} setNotas={setNotas} cadastros={cadastros} />

        {erro && <div className={ui.erro}>{erro}</div>}

        <div className={ui.botoes}>
          <button className={ui.botao} disabled={enviando}>
            {enviando ? 'Enviando…' : corrigindo ? 'Reenviar para conferência' : 'Enviar'}
          </button>
          <Link to={corrigindo ? `/solicitacoes/${id}` : '/inicio'} className={`${ui.botao} ${ui.secundario}`}>
            Cancelar
          </Link>
        </div>
      </form>
    </section>
  )
}
