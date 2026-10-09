import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { useContexto } from '@/components/contexto'
import { useApi } from '@/hooks/useApi'
import { api } from '@/services/api'
import ui from '@/styles/ui.module.css'
import type { Cadastros, Gestor, Solicitacao } from '@/types'
import { calcularDiarias, formatarMoeda, lerValor, mensagemErro } from '@/utils'

// Adiantamento de viagem: o colaborador pede ANTES de viajar e recebe as
// diárias (valor da diária vezes os dias) ou, se recebe auxílio refeição, a
// diária complementar (valor que ele informa). O gestor aprova, o financeiro
// paga e, depois da viagem, o colaborador presta contas com as notas.
// Também serve para corrigir um pedido devolvido (/solicitacoes/:id/corrigir-adiantamento).
export default function AdiantamentoFormPage() {
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
  const [complementar, setComplementar] = useState(false)
  const [valorComplementar, setValorComplementar] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    if (!pulaGestor)
      api.get<Gestor[]>('/api/gestores').then((r) => {
        setGestores(r.data)
        setGestoresCarregados(true)
      })
  }, [pulaGestor])

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
      setComplementar(s.diaria_complementar)
      setValorComplementar(
        s.diaria_complementar ? Number(s.valor_total).toFixed(2).replace('.', ',') : ''
      )
    })
  }, [id, cadastros])

  const valorDiaria = Number(cadastros?.valor_diaria ?? 0)
  const maxDiarias = cadastros?.max_diarias ?? 0
  const diarias = calcularDiarias(inicio, fim)
  const numeroComplementar = lerValor(valorComplementar)
  const valor = complementar
    ? Number.isNaN(numeroComplementar)
      ? 0
      : numeroComplementar
    : diarias * valorDiaria
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
      ...(complementar ? { diaria_complementar: valorComplementar } : {}),
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
            {corrigindo ? `Corrigir ${original?.codigo ?? ''}` : 'Novo adiantamento de viagem'}
          </h1>
          <p className={ui.muted}>
            {perfil.matricula} · {perfil.centro_custo?.rotulo}
          </p>
        </div>
      </div>

      {!corrigindo && (
        <div className={ui.info} style={{ marginBottom: 16 }}>
          Peça antes de viajar: você recebe as diárias adiantadas. Depois da viagem, faça a
          prestação de contas com as notas (prazo de 60 dias depois da volta). Se sobrar, você
          devolve; se faltar, recebe a diferença. Viagem internacional não tem adiantamento: peça
          o reembolso de viagem depois, com as notas.
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

        <fieldset className={ui.campo} style={{ border: 0, padding: 0, margin: 0 }}>
          <legend style={{ fontWeight: 600, fontSize: '0.9rem', marginBottom: 6 }}>Diárias</legend>
          <label style={{ fontWeight: 400 }}>
            <input
              type="radio"
              name="tipoDiaria"
              checked={!complementar}
              onChange={() => setComplementar(false)}
            />{' '}
            Diárias normais ({formatarMoeda(valorDiaria)} por dia)
          </label>
          <label style={{ fontWeight: 400 }}>
            <input
              type="radio"
              name="tipoDiaria"
              checked={complementar}
              onChange={() => setComplementar(true)}
            />{' '}
            Diária complementar — recebo auxílio refeição (trabalho 100% presencial no escritório)
          </label>
        </fieldset>
        {complementar && (
          <div className={ui.campo}>
            <label htmlFor="valorComplementar">Valor da diária complementar (R$)</label>
            <input
              id="valorComplementar"
              inputMode="decimal"
              placeholder="0,00"
              value={valorComplementar}
              onChange={(e) => setValorComplementar(e.target.value)}
              required
            />
            <span className={ui.ajuda}>Não tem valor fixo: informe o total que você precisa.</span>
          </div>
        )}

        <div className={ui.info} aria-live="polite">
          {diarias === 0 ? (
            'Informe a ida e a volta para calcular as diárias.'
          ) : complementar ? (
            <strong>
              Diária complementar: {formatarMoeda(valor)} ({diarias} dia{diarias > 1 ? 's' : ''} de
              viagem)
            </strong>
          ) : (
            <>
              <strong>
                {diarias} diária{diarias > 1 ? 's' : ''} × {formatarMoeda(valorDiaria)} ={' '}
                {formatarMoeda(valor)}
              </strong>
              <div className={ui.ajuda}>Conta o dia da ida e o da volta.</div>
            </>
          )}
        </div>
        {maxDiarias > 0 && diarias > maxDiarias && (
          <div className={ui.erro}>
            Período longo demais ({diarias} dias). Confira as datas (máximo {maxDiarias} diárias).
          </div>
        )}
        {limite > 0 && valor > limite && diarias <= maxDiarias && (
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
          <p className={ui.ajuda}>Como você é gestor, o pedido vai direto para o financeiro pagar.</p>
        )}

        {erro && <div className={ui.erro}>{erro}</div>}

        <div className={ui.botoes}>
          <button className={ui.botao} disabled={enviando || (maxDiarias > 0 && diarias > maxDiarias)}>
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
