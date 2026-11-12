import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import {
  BENEFICIARIO_VAZIO,
  beneficiarioEhGestor,
  camposBeneficiario,
  type BeneficiarioForm,
} from '@/beneficiario'
import BeneficiarioCampos from '@/components/BeneficiarioCampos'
import { useContexto } from '@/components/contexto'
import { useApi } from '@/hooks/useApi'
import { api } from '@/services/api'
import ui from '@/styles/ui.module.css'
import type { Cadastros, Gestor, Solicitacao } from '@/types'
import { formatarMoeda, lerValor, mensagemErro } from '@/utils'

// Adiantamento (Thais, 15/10): o colaborador pede ANTES de viajar e informa o
// valor do adiantamento (sem cálculo por dia; viagem internacional também pode).
// O gestor aprova, o financeiro paga e, depois da viagem, o colaborador presta
// contas com as notas. Não tem centro de custo.
// Também serve para corrigir um pedido devolvido antes de 15/10
// (/solicitacoes/:id/corrigir-adiantamento).
export default function AdiantamentoFormPage() {
  const { id } = useParams()
  const corrigindo = Boolean(id)
  const { tem, perfil } = useContexto()
  const navigate = useNavigate()

  const { data: cadastros } = useApi<Cadastros>('/api/cadastros')
  const [gestores, setGestores] = useState<Gestor[]>([])
  const [gestoresCarregados, setGestoresCarregados] = useState(false)
  const [original, setOriginal] = useState<Solicitacao | null>(null)
  const [benef, setBenef] = useState<BeneficiarioForm>(BENEFICIARIO_VAZIO)
  // Gestor pedindo (ou pedido em nome de um gestor) pula a aprovação de gestor.
  const pulaGestor = corrigindo
    ? (original?.pula_gestor ?? tem('gestor'))
    : benef.ativo
      ? beneficiarioEhGestor(benef, gestores)
      : tem('gestor')

  const [destino, setDestino] = useState('')
  const [inicio, setInicio] = useState('')
  const [fim, setFim] = useState('')
  const [descricao, setDescricao] = useState('')
  const [empresaEscolhida, setEmpresa] = useState('')
  const [gestor, setGestor] = useState('')
  const [valorPedido, setValorPedido] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  // A lista de gestores também diz se a pessoa do pedido é gestora.
  useEffect(() => {
    api.get<Gestor[]>('/api/gestores').then((r) => {
      setGestores(r.data)
      setGestoresCarregados(true)
    })
  }, [])

  // Só uma empresa de débito ativa (hoje, só a Tecnored): já vem escolhida.
  const empresa =
    empresaEscolhida ||
    (!corrigindo && cadastros?.empresas.length === 1 ? String(cadastros.empresas[0].id) : '')

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
      setValorPedido(Number(s.valor_total).toFixed(2).replace('.', ','))
    })
  }, [id, cadastros])

  const numeroValor = lerValor(valorPedido)
  const valor = Number.isNaN(numeroValor) ? 0 : numeroValor
  const limite = Number(cadastros?.limite_solicitacao ?? 0)

  async function enviar(e: FormEvent) {
    e.preventDefault()
    setErro(null)
    const corpo = {
      destino,
      viagem_inicio: inicio,
      viagem_fim: fim,
      descricao,
      empresa_id: Number(empresa),
      ...(pulaGestor ? {} : { gestor_email: gestor }),
      valor: valorPedido,
      ...(corrigindo ? {} : camposBeneficiario(benef)),
    }
    setEnviando(true)
    try {
      const url = corrigindo
        ? `/api/solicitacoes/${id}/reenviar-adiantamento`
        : '/api/solicitacoes/adiantamento'
      const res = await api.post<Solicitacao>(url, corpo)
      navigate(`/solicitacoes/${res.data.id}`, { replace: true, state: { enviado: true } })
    } catch (err) {
      setErro(mensagemErro(err))
    } finally {
      setEnviando(false)
    }
  }

  if (!perfil.completo) return <Navigate to="/perfil?voltar=/nova/adiantamento" replace />

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
            {corrigindo ? `Corrigir ${original?.codigo ?? ''}` : 'Adiantamento'}
          </h1>
          <p className={ui.muted}>
            {benef.ativo && benef.email.trim()
              ? `Em nome de ${benef.conhecido?.nome ?? (benef.nome || benef.email.trim())}`
              : `Matrícula ${perfil.matricula}`}
          </p>
        </div>
      </div>

      {!corrigindo && (
        <div className={ui.info} style={{ marginBottom: 16 }}>
          Atente-se aos limites estabelecidos em procedimento.
        </div>
      )}

      {original?.motivo_devolucao && (
        <div className={ui.aviso} style={{ marginBottom: 16 }}>
          <strong>Devolvida por {original.devolvido_por}:</strong> {original.motivo_devolucao}
        </div>
      )}

      <form className={ui.form} onSubmit={enviar}>
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
            <label htmlFor="inicio">Ida</label>
            <input id="inicio" type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} required />
          </div>
          <div className={ui.campo}>
            <label htmlFor="fim">Volta</label>
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
          <label htmlFor="valorPedido">Valor do adiantamento (R$)</label>
          <input
            id="valorPedido"
            inputMode="decimal"
            placeholder="0,00"
            value={valorPedido}
            onChange={(e) => setValorPedido(e.target.value)}
            required
          />
          <span className={ui.ajuda}>
            Depois da viagem, você presta contas com as notas (prazo de 60 dias depois da volta).
            Se sobrar, devolve; se faltar, recebe a diferença.
          </span>
        </div>
        {limite > 0 && valor > limite && (
          <div className={ui.aviso}>
            Total acima do limite por solicitação ({formatarMoeda(limite)}). Você pode enviar mesmo
            assim — o gestor e o financeiro vão ver o alerta.
          </div>
        )}

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

        <h2 className={ui.blocoTitulo}>Quem paga e quem aprova</h2>
        {!corrigindo && <BeneficiarioCampos valor={benef} onChange={setBenef} />}

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
                {gestores
                  .filter((g) => g.email !== benef.email.trim().toLowerCase())
                  .map((g) => (
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
          <p className={ui.ajuda}>{benef.ativo ? 'Como essa pessoa é gestora,' : 'Como você é gestor,'} o pedido vai direto para o financeiro pagar.</p>
        )}

        {erro && <div className={ui.erro}>{erro}</div>}

        <div className={`${ui.botoes} ${ui.barraAcao}`}>
          <button className={ui.botao} disabled={enviando}>
            {enviando ? 'Enviando…' : corrigindo ? 'Reenviar para o gestor' : 'Pedir adiantamento'}
          </button>
          <Link to={corrigindo ? `/solicitacoes/${id}` : '/inicio'} className={`${ui.botao} ${ui.secundario}`}>
            Cancelar
          </Link>
        </div>
      </form>
    </section>
  )
}
