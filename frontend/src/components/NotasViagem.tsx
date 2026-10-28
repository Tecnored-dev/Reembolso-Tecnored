import { useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from 'react'
import Icone from '@/components/Icone'
import {
  CATEGORIA_KM,
  aplicarLeitura,
  editarNota,
  limparLeitura,
  novaNota,
  valorDaQuilometragem,
  type CampoLidoNota,
  type NotaForm,
} from '@/notas'
import { analisarComprovante } from '@/services/comprovantes'
import ui from '@/styles/ui.module.css'
import type { AnaliseComprovante, Cadastros, CategoriaViagem, EstadoCampoLido } from '@/types'
import {
  alertasViagem,
  formatarCnpj,
  formatarData,
  formatarMoeda,
  hojeISO,
  lerValor,
  somarValores,
} from '@/utils'
import styles from './NotasViagem.module.css'

const ACEITOS = 'image/jpeg,image/png,application/pdf'
// Tipo em que a descrição é obrigatória (mesma regra da API).
const DESCRICAO_OBRIGATORIA = 'despesas_diversas'
const MAX_NOTAS = 30
const FALHA_LEITURA = 'A leitura automática não funcionou agora. Preencha os dados à mão.'

interface Props {
  notas: NotaForm[]
  setNotas: Dispatch<SetStateAction<NotaForm[]>>
  cadastros: Cadastros | null
  /** Categorias que a nota aceita (padrão: todas as de viagem, menos a quilometragem se `semKm`). */
  categoriasDoTipo?: { id: CategoriaViagem; rotulo: string }[]
  /** Prestação de contas do adiantamento: sem quilometragem (só vale no reembolso). */
  semKm?: boolean
  /** Limite de refeição por dia (padrão: o da viagem, R$ 135). */
  limiteDia?: number
  /** Categorias que contam como refeição para o limite. */
  categoriasRefeicao?: string[]
  /** Ler o comprovante ao anexar e sugerir os campos (`leitura_comprovante` do /api/config). */
  lerComprovante?: boolean
}

/** Situação da leitura automática de uma nota (só na tela). */
type Leitura =
  | { fase: 'lendo' }
  | { fase: 'lida'; analise: AnaliseComprovante; preenchidos: number }
  | { fase: 'falhou'; mensagem: string }

// Miniatura da imagem escolhida, para o colaborador conferir a foto antes de enviar.
function Miniatura({ arquivo }: { arquivo: File }) {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    if (!arquivo.type.startsWith('image/')) {
      setUrl(null)
      return
    }
    const novo = URL.createObjectURL(arquivo)
    setUrl(novo)
    return () => URL.revokeObjectURL(novo)
  }, [arquivo])
  if (!url) return <span className={ui.ajuda}>PDF escolhido: {arquivo.name}</span>
  return <img src={url} alt="Prévia da nota" className={styles.miniatura} />
}

// Selo ao lado do rótulo: o campo veio da leitura da nota e precisa ser conferido.
function Selo({ estado }: { estado?: EstadoCampoLido }) {
  if (!estado) return null
  const confira = estado === 'ambiguo'
  return (
    <span className={`${styles.selo} ${confira ? styles.seloConfira : ''}`}>
      {confira ? 'Confira' : 'Lido da nota'}
    </span>
  )
}

function classeCampo(estado?: EstadoCampoLido): string | undefined {
  if (!estado) return undefined
  return estado === 'ambiguo' ? styles.campoConfira : styles.campoLido
}

// Resultado da leitura, logo abaixo do arquivo.
function ResumoLeitura({ leitura }: { leitura: Leitura }) {
  if (leitura.fase === 'lendo')
    return (
      <p className={styles.leitura}>
        <span className={styles.girando} aria-hidden="true" />
        Lendo a nota…
      </p>
    )
  if (leitura.fase === 'falhou' || leitura.analise.status === 'ilegivel')
    return (
      <p className={`${styles.leitura} ${styles.leituraFalhou}`}>
        <Icone nome="alerta" tamanho={18} />
        {leitura.fase === 'falhou'
          ? leitura.mensagem
          : 'Não conseguimos ler esta nota. Preencha os dados à mão.'}
      </p>
    )

  const { campos, avisos } = leitura.analise
  const extras = [
    campos.cnpj.valor && `CNPJ ${formatarCnpj(campos.cnpj.valor)}`,
    campos.numero_documento.valor && `nota nº ${campos.numero_documento.valor}`,
  ].filter(Boolean)
  return (
    <div className={styles.leitura}>
      <Icone nome="check" tamanho={18} />
      <div>
        {leitura.preenchidos > 0
          ? 'Preenchemos os campos marcados com a leitura da nota. Confira antes de enviar.'
          : 'Lemos a nota, mas não havia campo vazio para preencher.'}
        {extras.length > 0 && <span className={styles.leituraDetalhe}>{extras.join(' · ')}</span>}
        {avisos.map((aviso) => (
          <span key={aviso} className={`${styles.leituraDetalhe} ${styles.leituraAviso}`}>
            {aviso}
          </span>
        ))}
      </div>
    </div>
  )
}

function mensagemFalha(err: unknown): string {
  // 400 explica o problema do arquivo; 503 já vem com "preencha à mão".
  const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
  return typeof detail === 'string' ? detail : FALHA_LEITURA
}

// Lista de notas (categoria, data, valor, descrição e arquivo), com total e
// alertas da política. Usada no reembolso de despesas, no reembolso de viagem
// e na prestação de contas do adiantamento.
export default function NotasViagem({
  notas,
  setNotas,
  cadastros,
  categoriasDoTipo,
  semKm = false,
  limiteDia,
  categoriasRefeicao,
  lerComprovante = false,
}: Props) {
  const valorPorKm = Number(cadastros?.valor_km ?? 1)
  const maxPontos = cadastros?.max_pontos_percurso ?? 8
  const categorias = useMemo(
    () =>
      categoriasDoTipo ??
      (cadastros?.categorias_viagem ?? []).filter((c) => !(semKm && c.id === CATEGORIA_KM)),
    [cadastros, semKm, categoriasDoTipo]
  )
  // Nota de pedido antigo com categoria que o tipo não aceita mais (ex.: Uber na
  // alimentação): continua aparecendo, para dar para corrigir o pedido.
  function opcoesDaNota(atual: string) {
    if (!atual || categorias.some((c) => c.id === atual)) return categorias
    const rotulo =
      cadastros?.categorias_viagem.find((c) => c.id === atual)?.rotulo ??
      (atual === 'diversos' ? 'Despesas diversas' : atual)
    return [...categorias, { id: atual, rotulo }]
  }
  const total = useMemo(() => somarValores(notas.map((n) => n.valor)), [notas])
  const alertas = useMemo(
    () =>
      alertasViagem(
        notas.map((n) => ({ categoria: n.categoria, data: n.data, valor: n.valor })),
        limiteDia ?? Number(cadastros?.limite_refeicao_dia ?? 0),
        Number(cadastros?.limite_solicitacao ?? 0),
        categoriasRefeicao
      ),
    [notas, cadastros, limiteDia, categoriasRefeicao]
  )

  // Leitura automática: situação por nota e a requisição em andamento (para
  // cancelar se o arquivo for trocado ou a nota removida).
  const [leituras, setLeituras] = useState<Record<number, Leitura>>({})
  const controles = useRef(new Map<number, AbortController>())
  const notasAtuais = useRef(notas)
  useEffect(() => {
    notasAtuais.current = notas
  })
  useEffect(() => {
    const emAndamento = controles.current
    return () => emAndamento.forEach((c) => c.abort())
  }, [])

  function esquecerLeitura(chave: number) {
    controles.current.get(chave)?.abort()
    controles.current.delete(chave)
    setLeituras((atual) => Object.fromEntries(Object.entries(atual).filter(([c]) => Number(c) !== chave)))
  }

  async function ler(chave: number, arquivo: File) {
    const controle = new AbortController()
    controles.current.set(chave, controle)
    setLeituras((atual) => ({ ...atual, [chave]: { fase: 'lendo' } }))
    try {
      const analise = await analisarComprovante(arquivo, controle.signal)
      if (controle.signal.aborted) return
      const opcoes = {
        categorias: categorias.map((c) => c.id).filter((id) => id !== CATEGORIA_KM),
        hoje: hojeISO(),
      }
      const nota = notasAtuais.current.find((n) => n.chave === chave)
      const preenchidos = nota ? Object.keys(aplicarLeitura(nota, analise, opcoes).lidos ?? {}).length : 0
      setNotas((atual) => atual.map((n) => (n.chave === chave ? aplicarLeitura(n, analise, opcoes) : n)))
      setLeituras((atual) => ({ ...atual, [chave]: { fase: 'lida', analise, preenchidos } }))
    } catch (err) {
      if (controle.signal.aborted) return
      setLeituras((atual) => ({ ...atual, [chave]: { fase: 'falhou', mensagem: mensagemFalha(err) } }))
    } finally {
      if (controles.current.get(chave) === controle) controles.current.delete(chave)
    }
  }

  function mudarNota(chave: number, mudanca: Partial<NotaForm>) {
    setNotas((atual) =>
      atual.map((n) => {
        if (n.chave !== chave) return n
        const nova = editarNota(n, mudanca)
        // Quilometragem: o valor é sempre km x valor por km (a API refaz a conta).
        if (nova.categoria === CATEGORIA_KM) return { ...nova, valor: valorDaQuilometragem(nova.km, valorPorKm) }
        // Deixou de ser quilometragem: o valor calculado não vale mais.
        if (n.categoria === CATEGORIA_KM) return { ...nova, valor: '' }
        return nova
      })
    )
  }

  function mudarPonto(chave: number, indice: number, texto: string) {
    const nota = notas.find((n) => n.chave === chave)
    if (nota) mudarNota(chave, { percurso: nota.percurso.map((p, i) => (i === indice ? texto : p)) })
  }

  function adicionarParada(chave: number) {
    const nota = notas.find((n) => n.chave === chave)
    if (!nota || nota.percurso.length >= maxPontos) return
    // A parada entra antes do destino (o último ponto).
    const meio = nota.percurso.slice(0, -1)
    mudarNota(chave, { percurso: [...meio, '', nota.percurso[nota.percurso.length - 1]] })
  }

  function removerParada(chave: number, indice: number) {
    const nota = notas.find((n) => n.chave === chave)
    if (nota) mudarNota(chave, { percurso: nota.percurso.filter((_, i) => i !== indice) })
  }

  function escolherArquivo(chave: number, arquivo: File | null) {
    esquecerLeitura(chave)
    setNotas((atual) =>
      atual.map((n) => {
        if (n.chave !== chave) return n
        // Sem arquivo, o que veio da leitura dele não vale mais.
        return arquivo ? editarNota(n, { arquivo }) : limparLeitura(editarNota(n, { arquivo: null }))
      })
    )
    if (arquivo && lerComprovante) void ler(chave, arquivo)
  }

  function removerNota(chave: number) {
    esquecerLeitura(chave)
    setNotas((atual) => atual.filter((n) => n.chave !== chave))
  }

  // Outros valores lidos, quando o campo ficou ambíguo ("Também lemos: …").
  function alternativas(chave: number, campo: CampoLidoNota, estado?: EstadoCampoLido): string | null {
    const leitura = leituras[chave]
    if (estado !== 'ambiguo' || leitura?.fase !== 'lida') return null
    const lidas =
      campo === 'valor'
        ? leitura.analise.campos.valor_total.alternativas.map((v) => formatarMoeda(v))
        : campo === 'data'
          ? leitura.analise.campos.data.alternativas.map((d) => formatarData(d))
          : []
    return lidas.length ? `Também lemos: ${lidas.join(', ')}.` : null
  }

  return (
    <>
      <div className={styles.notas}>
        {notas.map((n, i) => {
          const leitura = leituras[n.chave]
          const altData = alternativas(n.chave, 'data', n.lidos?.data)
          const altValor = alternativas(n.chave, 'valor', n.lidos?.valor)
          const ehKm = n.categoria === CATEGORIA_KM
          return (
            <fieldset key={n.chave} className={styles.nota}>
              <div className={styles.notaCabecalho}>
                <span>Nota {i + 1}</span>
                {notas.length > 1 && (
                  <button type="button" className={styles.remover} onClick={() => removerNota(n.chave)}>
                    Remover
                  </button>
                )}
              </div>
              {!ehKm && (
              <div className={`${ui.campo} ${styles.anexo}`}>
                <label htmlFor={`arq-${n.chave}`}>
                  <Icone nome="camera" tamanho={20} />
                  {n.id ? 'Trocar a nota (opcional)' : 'Foto ou PDF da nota'}
                </label>
                <input
                  id={`arq-${n.chave}`}
                  type="file"
                  accept={ACEITOS}
                  onChange={(e) => escolherArquivo(n.chave, e.target.files?.[0] ?? null)}
                />
                {n.arquivo && <Miniatura arquivo={n.arquivo} />}
                {n.arquivoAtual && !n.arquivo && (
                  <span className={ui.ajuda}>Nota atual: {n.arquivoAtual}</span>
                )}
                <div aria-live="polite">{leitura && <ResumoLeitura leitura={leitura} />}</div>
              </div>
              )}
              <div className={styles.linha}>
                <div className={ui.campo}>
                  <label htmlFor={`cat-${n.chave}`}>
                    Categoria <Selo estado={n.lidos?.categoria} />
                  </label>
                  <select
                    id={`cat-${n.chave}`}
                    className={classeCampo(n.lidos?.categoria)}
                    value={n.categoria}
                    onChange={(e) => mudarNota(n.chave, { categoria: e.target.value as CategoriaViagem })}
                    required
                  >
                    <option value="">Selecione…</option>
                    {opcoesDaNota(n.categoria).map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.rotulo}
                      </option>
                    ))}
                  </select>
                </div>
                <div className={ui.campo}>
                  <label htmlFor={`data-${n.chave}`}>
                    Data <Selo estado={n.lidos?.data} />
                  </label>
                  <input
                    id={`data-${n.chave}`}
                    type="date"
                    className={classeCampo(n.lidos?.data)}
                    value={n.data}
                    max={hojeISO()}
                    onChange={(e) => mudarNota(n.chave, { data: e.target.value })}
                    required
                  />
                  {altData && <span className={ui.ajuda}>{altData}</span>}
                </div>
                {ehKm ? (
                  <div className={ui.campo}>
                    <label htmlFor={`km-${n.chave}`}>Km rodados</label>
                    <input
                      id={`km-${n.chave}`}
                      inputMode="decimal"
                      placeholder="0"
                      value={n.km}
                      onChange={(e) => mudarNota(n.chave, { km: e.target.value })}
                      required
                    />
                  </div>
                ) : (
                  <div className={ui.campo}>
                    <label htmlFor={`valor-${n.chave}`}>
                      Valor (R$) <Selo estado={n.lidos?.valor} />
                    </label>
                    <input
                      id={`valor-${n.chave}`}
                      inputMode="decimal"
                      placeholder="0,00"
                      className={classeCampo(n.lidos?.valor)}
                      value={n.valor}
                      onChange={(e) => mudarNota(n.chave, { valor: e.target.value })}
                      required
                    />
                    {altValor && <span className={ui.ajuda}>{altValor}</span>}
                  </div>
                )}
              </div>
              {ehKm && (
                <div className={styles.percurso}>
                  {n.percurso.map((ponto, i) => {
                    const ultimo = i === n.percurso.length - 1
                    const rotulo = i === 0 ? 'Origem' : ultimo ? 'Destino' : `Parada ${i}`
                    return (
                      <div key={i} className={ui.campo}>
                        <label htmlFor={`ponto-${n.chave}-${i}`}>{rotulo}</label>
                        <div className={styles.ponto}>
                          <input
                            id={`ponto-${n.chave}-${i}`}
                            value={ponto}
                            maxLength={200}
                            placeholder="Cidade, endereço ou ponto de referência"
                            onChange={(e) => mudarPonto(n.chave, i, e.target.value)}
                            required
                          />
                          {i > 0 && !ultimo && (
                            <button
                              type="button"
                              className={styles.remover}
                              onClick={() => removerParada(n.chave, i)}
                            >
                              Remover
                            </button>
                          )}
                        </div>
                      </div>
                    )
                  })}
                  <button
                    type="button"
                    className={`${ui.botao} ${ui.secundario}`}
                    disabled={n.percurso.length >= maxPontos}
                    onClick={() => adicionarParada(n.chave)}
                  >
                    <Icone nome="mais" tamanho={18} />
                    Adicionar parada
                  </button>
                  <span className={ui.ajuda}>
                    Ida e volta? Coloque o endereço de partida como origem, adicione a parada e volte ao
                    mesmo endereço no destino. Informe o total de km do percurso.
                  </span>
                  <p className={styles.resumoKm} aria-live="polite">
                    Valor por km: {formatarMoeda(valorPorKm)} · Valor da nota:{' '}
                    <strong>{n.valor ? formatarMoeda(lerValor(n.valor)) : '—'}</strong>
                  </p>
                </div>
              )}
              <div className={ui.campo}>
                <label htmlFor={`desc-${n.chave}`}>
                  Descrição {n.categoria === DESCRICAO_OBRIGATORIA || ehKm ? '' : '(opcional)'}{' '}
                  <Selo estado={n.lidos?.descricao} />
                </label>
                <input
                  id={`desc-${n.chave}`}
                  className={classeCampo(n.lidos?.descricao)}
                  value={n.descricao}
                  maxLength={200}
                  placeholder={
                    ehKm
                      ? 'Ex.: Visita ao cliente'
                      : n.categoria === DESCRICAO_OBRIGATORIA
                        ? 'Ex.: Cópias de documentos'
                        : ''
                  }
                  onChange={(e) => mudarNota(n.chave, { descricao: e.target.value })}
                  required={n.categoria === DESCRICAO_OBRIGATORIA || ehKm}
                />
              </div>
            </fieldset>
          )
        })}
      </div>

      <div className={styles.rodape}>
        <button
          type="button"
          className={`${ui.botao} ${ui.secundario}`}
          disabled={notas.length >= MAX_NOTAS}
          onClick={() => setNotas((atual) => [...atual, novaNota()])}
        >
          <Icone nome="mais" tamanho={18} />
          Adicionar nota
        </button>
        <span className={styles.total}>
          <span>Total</span> {formatarMoeda(total)}
        </span>
      </div>
      <span className={ui.ajuda}>
        JPG, PNG ou PDF, até 10 MB cada. No celular, dá para tirar a foto na hora.
        {lerComprovante && ' Ao anexar, lemos a nota e preenchemos o que der: confira antes de enviar.'}
      </span>

      {alertas.map((a) => (
        <div key={a} className={`${ui.aviso} ${styles.alerta}`}>
          <Icone nome="alerta" tamanho={20} />
          <span>{a} Você pode enviar mesmo assim — o financeiro vai ver o alerta.</span>
        </div>
      ))}
    </>
  )
}
