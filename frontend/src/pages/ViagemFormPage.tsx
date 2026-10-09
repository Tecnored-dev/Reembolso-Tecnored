import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { useContexto } from '@/components/contexto'
import { useApi } from '@/hooks/useApi'
import { api } from '@/services/api'
import ui from '@/styles/ui.module.css'
import type { Cadastros, CategoriaViagem, Gestor, Solicitacao } from '@/types'
import { alertasViagem, formatarMoeda, hojeISO, mensagemErro, somarValores } from '@/utils'
import styles from './ViagemFormPage.module.css'

const ACEITOS = 'image/jpeg,image/png,application/pdf'
const MAX_NOTAS = 30

interface NotaForm {
  chave: number
  /** Só na correção: nota que já foi enviada. */
  id?: number
  categoria: CategoriaViagem | ''
  data: string
  valor: string
  descricao: string
  arquivo: File | null
  /** Nome da nota já enviada (correção), mostrado enquanto não for trocada. */
  arquivoAtual?: string
}

let proximaChave = 1
function novaNota(): NotaForm {
  return { chave: proximaChave++, categoria: '', data: '', valor: '', descricao: '', arquivo: null }
}

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
      setNotas(
        s.despesas.map((d) => ({
          chave: proximaChave++,
          id: d.id,
          categoria: d.categoria as CategoriaViagem,
          data: d.data_despesa,
          valor: Number(d.valor).toFixed(2).replace('.', ','),
          descricao: d.descricao ?? '',
          arquivo: null,
          arquivoAtual: d.arquivo_nome,
        }))
      )
    })
  }, [id, cadastros])

  const total = useMemo(() => somarValores(notas.map((n) => n.valor)), [notas])
  const alertas = useMemo(
    () =>
      alertasViagem(
        notas.map((n) => ({ categoria: n.categoria, data: n.data, valor: n.valor })),
        Number(cadastros?.limite_refeicao_dia ?? 0),
        Number(cadastros?.limite_solicitacao ?? 0)
      ),
    [notas, cadastros]
  )

  function mudarNota(chave: number, mudanca: Partial<NotaForm>) {
    setNotas((atual) => atual.map((n) => (n.chave === chave ? { ...n, ...mudanca } : n)))
  }

  function removerNota(chave: number) {
    setNotas((atual) => atual.filter((n) => n.chave !== chave))
  }

  async function enviar(e: FormEvent) {
    e.preventDefault()
    setErro(null)
    if (notas.length === 0) {
      setErro('Inclua pelo menos uma nota.')
      return
    }
    const semArquivo = notas.findIndex((n) => !n.arquivo && !n.id)
    if (semArquivo >= 0) {
      setErro(`Nota ${semArquivo + 1}: anexe a foto ou o PDF.`)
      return
    }

    // Os arquivos vão numa lista; cada nota diz a posição do seu arquivo nela.
    const form = new FormData()
    const despesas = notas.map((n) => {
      let arquivo: number | undefined
      if (n.arquivo) {
        arquivo = form.getAll('arquivos').length
        form.append('arquivos', n.arquivo)
      }
      return {
        ...(n.id ? { id: n.id } : {}),
        categoria: n.categoria,
        data_despesa: n.data,
        valor: n.valor,
        descricao: n.descricao,
        ...(arquivo !== undefined ? { arquivo } : {}),
      }
    })
    form.append('destino', destino)
    form.append('viagem_inicio', inicio)
    form.append('viagem_fim', fim)
    form.append('descricao', descricao)
    form.append('empresa_id', empresa)
    if (!pulaGestor) form.append('gestor_email', gestor)
    form.append('despesas', JSON.stringify(despesas))

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
        <div className={styles.notas}>
          {notas.map((n, i) => (
            <fieldset key={n.chave} className={styles.nota}>
              <div className={styles.notaCabecalho}>
                <span>Nota {i + 1}</span>
                {notas.length > 1 && (
                  <button type="button" className={styles.remover} onClick={() => removerNota(n.chave)}>
                    Remover
                  </button>
                )}
              </div>
              <div className={styles.linha}>
                <div className={ui.campo}>
                  <label htmlFor={`cat-${n.chave}`}>Categoria</label>
                  <select
                    id={`cat-${n.chave}`}
                    value={n.categoria}
                    onChange={(e) => mudarNota(n.chave, { categoria: e.target.value as CategoriaViagem })}
                    required
                  >
                    <option value="">Selecione…</option>
                    {cadastros?.categorias_viagem.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.rotulo}
                      </option>
                    ))}
                  </select>
                </div>
                <div className={ui.campo}>
                  <label htmlFor={`data-${n.chave}`}>Data</label>
                  <input
                    id={`data-${n.chave}`}
                    type="date"
                    value={n.data}
                    max={hojeISO()}
                    onChange={(e) => mudarNota(n.chave, { data: e.target.value })}
                    required
                  />
                </div>
                <div className={ui.campo}>
                  <label htmlFor={`valor-${n.chave}`}>Valor (R$)</label>
                  <input
                    id={`valor-${n.chave}`}
                    inputMode="decimal"
                    placeholder="0,00"
                    value={n.valor}
                    onChange={(e) => mudarNota(n.chave, { valor: e.target.value })}
                    required
                  />
                </div>
              </div>
              <div className={ui.campo}>
                <label htmlFor={`desc-${n.chave}`}>
                  Descrição {n.categoria === 'outros' ? '' : '(opcional)'}
                </label>
                <input
                  id={`desc-${n.chave}`}
                  value={n.descricao}
                  maxLength={200}
                  placeholder={n.categoria === 'outros' ? 'Ex.: Estacionamento' : ''}
                  onChange={(e) => mudarNota(n.chave, { descricao: e.target.value })}
                  required={n.categoria === 'outros'}
                />
              </div>
              <div className={ui.campo}>
                <label htmlFor={`arq-${n.chave}`}>
                  {n.id ? 'Trocar a nota (opcional)' : 'Foto ou PDF da nota'}
                </label>
                <input
                  id={`arq-${n.chave}`}
                  type="file"
                  accept={ACEITOS}
                  onChange={(e) => mudarNota(n.chave, { arquivo: e.target.files?.[0] ?? null })}
                />
                {n.arquivoAtual && !n.arquivo && (
                  <span className={ui.ajuda}>Nota atual: {n.arquivoAtual}</span>
                )}
              </div>
            </fieldset>
          ))}
        </div>

        <div className={styles.rodape}>
          <button
            type="button"
            className={`${ui.botao} ${ui.secundario}`}
            disabled={notas.length >= MAX_NOTAS}
            onClick={() => setNotas((atual) => [...atual, novaNota()])}
          >
            + Adicionar nota
          </button>
          <span className={styles.total}>Total: {formatarMoeda(total)}</span>
        </div>
        <span className={ui.ajuda}>JPG, PNG ou PDF, até 10 MB cada. No celular, dá para tirar a foto na hora.</span>

        {alertas.map((a) => (
          <div key={a} className={ui.aviso}>
            {a} Você pode enviar mesmo assim — o financeiro vai ver o alerta.
          </div>
        ))}

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
