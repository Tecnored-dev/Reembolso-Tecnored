import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import {
  BENEFICIARIO_VAZIO,
  beneficiarioEhGestor,
  camposBeneficiario,
  type BeneficiarioForm,
} from '@/beneficiario'
import { centroCustoInicial } from '@/centroCusto'
import BeneficiarioCampos from '@/components/BeneficiarioCampos'
import CentroCustoCampo from '@/components/CentroCustoCampo'
import { useContexto } from '@/components/contexto'
import {
  linhasParaApi,
  novaLinhaDiaria,
  quantidadeDiarias,
  subtotalLinha,
  totalDiaria,
  type LinhaDiariaForm,
  type TipoLinhaDiaria,
} from '@/diaria'
import { useApi } from '@/hooks/useApi'
import { api } from '@/services/api'
import ui from '@/styles/ui.module.css'
import type { Cadastros, Gestor, Solicitacao } from '@/types'
import { calcularDiarias, formatarMoeda, mensagemErro } from '@/utils'

// Diária de Viagem (Thais, 15/10): destino, ida, volta, motivo, centro de custo
// e linhas de "Valor Integral" (valor fixo da política) ou "Valor Parcial" (valor
// informado), que podem se misturar. Sem notas e sem anexo; o total é calculado
// na hora. Viagem internacional não tem diária. Também serve para corrigir um
// pedido devolvido (/solicitacoes/:id/corrigir-viagem). Despesas com nota
// (hotel, Uber, passagem) vão no Reembolso de despesas.
export default function ViagemFormPage() {
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
  const [internacional, setInternacional] = useState(false)
  const [descricao, setDescricao] = useState('')
  const [empresaEscolhida, setEmpresa] = useState('')
  const [centroCustoEscolhido, setCentroCusto] = useState('')
  const [gestor, setGestor] = useState('')
  const [linhas, setLinhas] = useState<LinhaDiariaForm[]>(() => [novaLinhaDiaria()])
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

  // Pedido novo: o centro de custo vem com o último usado (dá para trocar).
  const centroCusto =
    centroCustoEscolhido ||
    (!corrigindo && cadastros ? centroCustoInicial(cadastros.centros_custo, perfil, null) : '')

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
      setCentroCusto(centroCustoInicial(cadastros.centros_custo, perfil, s))
      setGestor(s.gestor_email ?? '')
      if (s.linhas_diaria.length > 0)
        setLinhas(
          s.linhas_diaria.map((l) => ({
            tipo: l.tipo,
            quantidade: String(l.quantidade),
            valor: l.tipo === 'parcial' ? Number(l.valor_unitario).toFixed(2).replace('.', ',') : '',
          }))
        )
    })
  }, [id, cadastros, perfil])

  const valorDiaria = Number(cadastros?.valor_diaria ?? 0)
  const maxDiarias = cadastros?.max_diarias ?? 60
  const limite = Number(cadastros?.limite_solicitacao ?? 0)
  const total = totalDiaria(linhas, valorDiaria)
  const dias = calcularDiarias(inicio, fim)
  const quantidade = quantidadeDiarias(linhas)
  // Pedido antigo (com notas): não dá para corrigir, só abrir um novo.
  const antigo = corrigindo && original !== null && original.despesas.length > 0

  function mudarLinha(n: number, mudanca: Partial<LinhaDiariaForm>) {
    setLinhas((atuais) => atuais.map((l, i) => (i === n ? { ...l, ...mudanca } : l)))
  }

  async function enviar(e: FormEvent) {
    e.preventDefault()
    setErro(null)
    const corpo = {
      destino,
      viagem_inicio: inicio,
      viagem_fim: fim,
      descricao,
      empresa_id: Number(empresa),
      centro_custo_id: centroCusto,
      internacional,
      linhas: linhasParaApi(linhas),
      ...(pulaGestor ? {} : { gestor_email: gestor }),
      ...(corrigindo ? {} : camposBeneficiario(benef)),
    }
    setEnviando(true)
    try {
      const url = corrigindo ? `/api/solicitacoes/${id}/reenviar-viagem` : '/api/solicitacoes/viagem'
      const res = await api.post<Solicitacao>(url, corpo)
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

  if (antigo) {
    return (
      <section className={ui.card}>
        <div className={ui.aviso}>
          Este pedido é do modelo antigo de viagem (com notas) e não pode ser corrigido aqui. Abra
          uma nova Diária de Viagem; as despesas com nota vão no Reembolso de despesas.
        </div>
        <div className={`${ui.botoes} ${ui.barraAcao}`}>
          <Link to="/nova/viagem" className={ui.botao}>
            Nova diária de viagem
          </Link>
          <Link to={`/solicitacoes/${id}`} className={`${ui.botao} ${ui.secundario}`}>
            Voltar
          </Link>
        </div>
      </section>
    )
  }

  return (
    <section className={ui.card}>
      <div className={ui.cabecalho}>
        <div>
          <h1 className={ui.titulo}>
            {corrigindo ? `Corrigir ${original?.codigo ?? ''}` : 'Diária de Viagem'}
          </h1>
          <p className={ui.muted}>
            {benef.ativo && benef.email.trim()
              ? `Em nome de ${benef.conhecido?.nome ?? (benef.nome || benef.email.trim())}`
              : `Matrícula ${perfil.matricula}`}
          </p>
        </div>
      </div>

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

        <fieldset className={ui.campo} style={{ border: 'none', padding: 0 }}>
          <legend style={{ fontWeight: 600, marginBottom: 6 }}>Viagem internacional?</legend>
          <label className={ui.opcao}>
            <input
              type="radio"
              name="internacional"
              checked={!internacional}
              onChange={() => setInternacional(false)}
            />{' '}
            Não
          </label>
          <label className={ui.opcao}>
            <input
              type="radio"
              name="internacional"
              checked={internacional}
              onChange={() => setInternacional(true)}
            />{' '}
            Sim
          </label>
        </fieldset>
        {internacional && (
          <div className={ui.aviso}>
            Viagem internacional não tem diária. Se precisar de um valor antes de viajar, peça um
            Adiantamento; as despesas com nota vão no Reembolso de despesas.
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

        <h2 className={ui.blocoTitulo}>Diárias</h2>
        {linhas.map((linha, n) => (
          <div key={n} className={ui.grade} data-testid="linha-diaria">
            <div className={ui.campo}>
              <label htmlFor={`tipo-${n}`}>Categoria</label>
              <select
                id={`tipo-${n}`}
                value={linha.tipo}
                onChange={(e) => mudarLinha(n, { tipo: e.target.value as TipoLinhaDiaria })}
              >
                <option value="integral">Valor Integral ({formatarMoeda(valorDiaria)})</option>
                <option value="parcial">Valor Parcial</option>
              </select>
            </div>
            <div className={ui.campo}>
              <label htmlFor={`qtd-${n}`}>Quantidade de diárias</label>
              <input
                id={`qtd-${n}`}
                type="number"
                min={1}
                max={maxDiarias}
                step={1}
                value={linha.quantidade}
                onChange={(e) => mudarLinha(n, { quantidade: e.target.value })}
                required
              />
            </div>
            {linha.tipo === 'parcial' && (
              <div className={ui.campo}>
                <label htmlFor={`valor-${n}`}>Valor da diária (R$)</label>
                <input
                  id={`valor-${n}`}
                  inputMode="decimal"
                  placeholder="0,00"
                  value={linha.valor}
                  onChange={(e) => mudarLinha(n, { valor: e.target.value })}
                  required
                />
              </div>
            )}
            <div className={ui.campo}>
              <span style={{ fontWeight: 600 }}>Subtotal</span>
              <span>{formatarMoeda(subtotalLinha(linha, valorDiaria))}</span>
              {linhas.length > 1 && (
                <button
                  type="button"
                  className={`${ui.botao} ${ui.secundario}`}
                  onClick={() => setLinhas((atuais) => atuais.filter((_, i) => i !== n))}
                >
                  Remover
                </button>
              )}
            </div>
          </div>
        ))}
        <div>
          <button
            type="button"
            className={`${ui.botao} ${ui.secundario}`}
            onClick={() => setLinhas((atuais) => [...atuais, novaLinhaDiaria()])}
          >
            + Adicionar linha
          </button>
        </div>

        <div className={ui.totalDestaque} aria-live="polite">
          <span>Total das diárias</span>
          <strong>{formatarMoeda(total)}</strong>
        </div>
        {dias > 0 && quantidade > dias && (
          <div className={ui.aviso}>
            A quantidade de diárias ({quantidade}) é maior que os dias da viagem ({dias}). Você pode
            enviar mesmo assim — o financeiro vai ver o alerta.
          </div>
        )}
        {limite > 0 && total > limite && (
          <div className={ui.aviso}>
            Total acima do limite por solicitação ({formatarMoeda(limite)}). Você pode enviar mesmo
            assim — o gestor e o financeiro vão ver o alerta.
          </div>
        )}

        <h2 className={ui.blocoTitulo}>Quem paga e quem aprova</h2>
        {!corrigindo && <BeneficiarioCampos valor={benef} onChange={setBenef} />}

        <CentroCustoCampo
          centros={cadastros?.centros_custo ?? []}
          valor={centroCusto}
          onChange={setCentroCusto}
        />

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
          <p className={ui.ajuda}>
            {benef.ativo ? 'Como essa pessoa é gestora,' : 'Como você é gestor,'} depois da conferência do financeiro segue direto para pagamento.
          </p>
        )}

        {erro && <div className={ui.erro}>{erro}</div>}

        <div className={`${ui.botoes} ${ui.barraAcao}`}>
          <button className={ui.botao} disabled={enviando || internacional}>
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
