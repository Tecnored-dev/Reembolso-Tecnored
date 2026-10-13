import { useEffect, useMemo, useState, type FormEvent } from 'react'
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
import { formatarMoeda, hojeISO, lerValor, mensagemErro } from '@/utils'
import styles from './AlimentacaoFormPage.module.css'

const ACEITOS = 'image/jpeg,image/png,application/pdf'

// Novo reembolso de alimentação, ou correção de um devolvido (/solicitacoes/:id/corrigir).
// Uma nota por solicitação. O gestor só é pedido de quem não é gestor
// (gestor pedindo pula a aprovação de gestor).
export default function AlimentacaoFormPage() {
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

  const [data, setData] = useState(hojeISO())
  const [valor, setValor] = useState('')
  const [descricao, setDescricao] = useState('')
  const [empresa, setEmpresa] = useState('')
  const [gestor, setGestor] = useState('')
  const [arquivo, setArquivo] = useState<File | null>(null)
  const [previa, setPrevia] = useState<string | null>(null)
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
  useEffect(() => {
    if (!corrigindo && cadastros?.empresas.length === 1)
      setEmpresa(String(cadastros.empresas[0].id))
  }, [cadastros, corrigindo])

  // Correção: carrega o que foi enviado para editar em cima.
  useEffect(() => {
    if (!id || !cadastros) return
    api.get<Solicitacao>(`/api/solicitacoes/${id}`).then((r) => {
      const s = r.data
      setOriginal(s)
      setData(s.despesas[0]?.data_despesa ?? hojeISO())
      setValor(Number(s.valor_total).toFixed(2).replace('.', ','))
      setDescricao(s.descricao)
      setEmpresa(String(cadastros.empresas.find((e) => e.nome === s.empresa)?.id ?? ''))
      setGestor(s.gestor_email ?? '')
    })
  }, [id, cadastros])

  useEffect(() => {
    if (!arquivo || !arquivo.type.startsWith('image/')) {
      setPrevia(null)
      return
    }
    const url = URL.createObjectURL(arquivo)
    setPrevia(url)
    return () => URL.revokeObjectURL(url)
  }, [arquivo])

  const limite = Number(cadastros?.limite_refeicao_dia ?? 0)
  const numero = useMemo(() => lerValor(valor), [valor])
  const acimaDoLimite = limite > 0 && numero > limite

  async function enviar(e: FormEvent) {
    e.preventDefault()
    setErro(null)
    if (!corrigindo && !arquivo) {
      setErro('Anexe a foto ou o PDF da nota.')
      return
    }
    const form = new FormData()
    form.append('data_despesa', data)
    form.append('valor', valor)
    form.append('descricao', descricao)
    form.append('empresa_id', empresa)
    if (!pulaGestor) form.append('gestor_email', gestor)
    if (!corrigindo)
      for (const [campo, conteudo] of Object.entries(camposBeneficiario(benef)))
        form.append(campo, conteudo)
    if (arquivo) form.append('arquivo', arquivo)

    setEnviando(true)
    try {
      const url = corrigindo ? `/api/solicitacoes/${id}/reenviar` : '/api/solicitacoes/alimentacao'
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
            {corrigindo ? `Corrigir ${original?.codigo ?? ''}` : 'Novo reembolso de alimentação'}
          </h1>
          <p className={ui.muted}>
            {benef.ativo && benef.email.trim()
              ? `Em nome de ${benef.conhecido?.nome ?? (benef.nome || benef.email.trim())}`
              : `${perfil.matricula} · ${perfil.centro_custo?.rotulo ?? ''}`}
          </p>
        </div>
      </div>

      {original?.motivo_devolucao && (
        <div className={ui.aviso} style={{ marginBottom: 16 }}>
          <strong>Devolvida por {original.devolvido_por}:</strong> {original.motivo_devolucao}
        </div>
      )}

      <form className={ui.form} onSubmit={enviar}>
        <div className={ui.grade}>
          <div className={ui.campo}>
            <label htmlFor="data">Data da despesa</label>
            <input
              id="data"
              type="date"
              value={data}
              max={hojeISO()}
              onChange={(e) => setData(e.target.value)}
              required
            />
          </div>
          <div className={ui.campo}>
            <label htmlFor="valor">Valor (R$)</label>
            <input
              id="valor"
              inputMode="decimal"
              placeholder="0,00"
              value={valor}
              onChange={(e) => setValor(e.target.value)}
              required
            />
          </div>
        </div>

        {acimaDoLimite && (
          <div className={ui.aviso}>
            Acima do limite diário de refeição da política ({formatarMoeda(limite)}). Você pode
            enviar mesmo assim — o financeiro vai ver o alerta.
          </div>
        )}

        <div className={ui.campo}>
          <label htmlFor="descricao">Descrição</label>
          <textarea
            id="descricao"
            value={descricao}
            maxLength={500}
            placeholder="Ex.: Almoço com cliente na visita técnica"
            onChange={(e) => setDescricao(e.target.value)}
            required
          />
          <span className={ui.ajuda}>{descricao.length}/500</span>
        </div>

        {!corrigindo && (
          <BeneficiarioCampos
            valor={benef}
            onChange={setBenef}
            centros={cadastros?.centros_custo ?? []}
          />
        )}

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

        <div className={ui.campo}>
          <label htmlFor="arquivo">
            {corrigindo ? 'Trocar a nota (opcional)' : 'Foto ou PDF da nota'}
          </label>
          <input
            id="arquivo"
            type="file"
            accept={ACEITOS}
            onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
          />
          <span className={ui.ajuda}>JPG, PNG ou PDF, até 10 MB. No celular, dá para tirar a foto na hora.</span>
          {previa && <img src={previa} alt="Prévia da nota" className={styles.previa} />}
        </div>

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
