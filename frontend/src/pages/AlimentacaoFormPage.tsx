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
import NotasViagem from '@/components/NotasViagem'
import { useApi } from '@/hooks/useApi'
import { anexarNotas, conferirNotas, novaNota, notasEnviadas, type NotaForm } from '@/notas'
import { api } from '@/services/api'
import ui from '@/styles/ui.module.css'
import type { Cadastros, Gestor, Solicitacao, TipoDespesas } from '@/types'
import { mensagemErro } from '@/utils'

// "Reembolso de despesas - Prestação de Contas" (Thais, 15/10): o colaborador
// escolhe alimentação ou despesas diversas e lança uma ou mais notas. Na
// alimentação, cada nota tem categoria (mesma lista das notas de viagem) e a
// refeição tem limite de R$ 40 por dia (só aviso). Também serve para corrigir
// um pedido devolvido (/solicitacoes/:id/corrigir), inclusive os antigos, de
// uma nota só. O gestor só é pedido de quem não é gestor.
interface Props {
  tipo?: TipoDespesas
}

const TIPOS: { id: TipoDespesas; rotulo: string; ajuda: string; exemplo: string }[] = [
  {
    id: 'alimentacao',
    rotulo: 'Reembolso de alimentação',
    ajuda: 'Refeições e demais gastos com nota (Uber, combustível, estacionamento…). Escolha a categoria de cada nota.',
    exemplo: 'Ex.: Visita técnica ao cliente em Taubaté',
  },
  {
    id: 'diversas',
    rotulo: 'Despesas diversas',
    ajuda: 'Despesas que não se encaixam nas categorias — por exemplo, um carregador ou créditos de celular.',
    exemplo: 'Ex.: Carregador de notebook para a visita técnica',
  },
]

// Categorias que contam para o limite de refeição da alimentação (mesma regra da API).
const CATEGORIAS_REFEICAO = ['refeicao', 'almoco_pinda']

export default function AlimentacaoFormPage({ tipo: tipoPedido = 'alimentacao' }: Props) {
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

  const [escolhido, setEscolhido] = useState<TipoDespesas>(tipoPedido)
  const [descricao, setDescricao] = useState('')
  const [motivo, setMotivo] = useState('')
  const [empresa, setEmpresa] = useState('')
  const [centroCusto, setCentroCusto] = useState('')
  const [gestor, setGestor] = useState('')
  const [notas, setNotas] = useState<NotaForm[]>(() => [novaNota()])
  const [erro, setErro] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  // Na correção, o tipo é o do pedido devolvido.
  const tipo: TipoDespesas = original ? (original.tipo === 'diversas' ? 'diversas' : 'alimentacao') : escolhido
  const texto = TIPOS.find((t) => t.id === tipo) ?? TIPOS[0]

  // A lista de gestores também diz se a pessoa do pedido é gestora.
  useEffect(() => {
    api.get<Gestor[]>('/api/gestores').then((r) => {
      setGestores(r.data)
      setGestoresCarregados(true)
    })
  }, [])

  // Só uma empresa de débito ativa (hoje, só a Tecnored): já vem escolhida.
  useEffect(() => {
    if (!corrigindo && cadastros?.empresas.length === 1)
      setEmpresa(String(cadastros.empresas[0].id))
  }, [cadastros, corrigindo])

  // Pedido novo: o centro de custo vem com o último usado (dá para trocar).
  useEffect(() => {
    if (!corrigindo && cadastros)
      setCentroCusto((atual) => atual || centroCustoInicial(cadastros.centros_custo, perfil, null))
  }, [cadastros, corrigindo, perfil])

  // Correção: carrega o que foi enviado para editar em cima.
  useEffect(() => {
    if (!id || !cadastros) return
    api.get<Solicitacao>(`/api/solicitacoes/${id}`).then((r) => {
      const s = r.data
      setOriginal(s)
      setDescricao(s.descricao)
      setMotivo(s.motivo ?? '')
      setEmpresa(String(cadastros.empresas.find((e) => e.nome === s.empresa)?.id ?? ''))
      setCentroCusto(centroCustoInicial(cadastros.centros_custo, perfil, s))
      setGestor(s.gestor_email ?? '')
      setNotas(notasEnviadas(s.despesas))
    })
  }, [id, cadastros, perfil])

  async function enviar(e: FormEvent) {
    e.preventDefault()
    setErro(null)
    const problema = conferirNotas(notas)
    if (problema) {
      setErro(problema)
      return
    }
    const form = new FormData()
    anexarNotas(form, tipo === 'diversas' ? notas.map((n) => ({ ...n, categoria: 'diversos' })) : notas)
    form.append('descricao', descricao)
    form.append('motivo', motivo)
    form.append('empresa_id', empresa)
    form.append('centro_custo_id', centroCusto)
    if (!pulaGestor) form.append('gestor_email', gestor)
    if (!corrigindo)
      for (const [campo, conteudo] of Object.entries(camposBeneficiario(benef)))
        form.append(campo, conteudo)

    setEnviando(true)
    try {
      const url = corrigindo ? `/api/solicitacoes/${id}/reenviar` : `/api/solicitacoes/${tipo}`
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

  if (!perfil.completo) return <Navigate to="/perfil?voltar=/nova" replace />

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
            {corrigindo ? `Corrigir ${original?.codigo ?? ''}` : 'Reembolso de despesas - Prestação de Contas'}
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
        <fieldset className={ui.campo} style={{ border: 'none', padding: 0 }}>
          <legend style={{ fontWeight: 600, marginBottom: 6 }}>Tipo de reembolso</legend>
          {corrigindo ? (
            <span>{texto.rotulo}</span>
          ) : (
            TIPOS.map((t) => (
              <label key={t.id} style={{ fontWeight: 400 }}>
                <input
                  type="radio"
                  name="tipo"
                  value={t.id}
                  checked={escolhido === t.id}
                  onChange={() => setEscolhido(t.id)}
                />{' '}
                {t.rotulo}
              </label>
            ))
          )}
          <span className={ui.ajuda}>{texto.ajuda}</span>
        </fieldset>

        <div className={ui.campo}>
          <label htmlFor="motivo">Motivo</label>
          <select id="motivo" value={motivo} onChange={(e) => setMotivo(e.target.value)} required>
            <option value="">Selecione…</option>
            {cadastros?.motivos.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>

        <div className={ui.campo}>
          <label htmlFor="descricao">Descrição</label>
          <textarea
            id="descricao"
            value={descricao}
            maxLength={500}
            placeholder={texto.exemplo}
            onChange={(e) => setDescricao(e.target.value)}
            required
          />
          <span className={ui.ajuda}>{descricao.length}/500</span>
        </div>

        <h2 className={ui.blocoTitulo}>Notas</h2>
        <NotasViagem
          notas={notas}
          setNotas={setNotas}
          cadastros={cadastros}
          semCategoria={tipo === 'diversas'}
          limiteDia={Number(cadastros?.limite_alimentacao_dia ?? 0)}
          categoriasRefeicao={CATEGORIAS_REFEICAO}
        />

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
