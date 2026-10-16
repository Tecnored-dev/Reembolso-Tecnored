import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from 'react'
import Icone from '@/components/Icone'
import { novaNota, type NotaForm } from '@/notas'
import ui from '@/styles/ui.module.css'
import type { Cadastros, CategoriaViagem } from '@/types'
import { alertasViagem, formatarMoeda, hojeISO, somarValores } from '@/utils'
import styles from './NotasViagem.module.css'

const ACEITOS = 'image/jpeg,image/png,application/pdf'
// Tipo em que a descrição é obrigatória (mesma regra da API).
const DESCRICAO_OBRIGATORIA = 'despesas_diversas'
const MAX_NOTAS = 30

interface Props {
  notas: NotaForm[]
  setNotas: Dispatch<SetStateAction<NotaForm[]>>
  cadastros: Cadastros | null
  /** Despesas diversas: as notas não têm categoria. */
  semCategoria?: boolean
  /** Limite de refeição por dia (padrão: o da viagem, R$ 135). */
  limiteDia?: number
  /** Categorias que contam como refeição para o limite. */
  categoriasRefeicao?: string[]
}

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

// Lista de notas (categoria, data, valor, descrição e arquivo), com total e
// alertas da política. Usada no reembolso de despesas, no reembolso de viagem
// e na prestação de contas do adiantamento.
export default function NotasViagem({
  notas,
  setNotas,
  cadastros,
  semCategoria = false,
  limiteDia,
  categoriasRefeicao,
}: Props) {
  const total = useMemo(() => somarValores(notas.map((n) => n.valor)), [notas])
  const alertas = useMemo(
    () =>
      alertasViagem(
        notas.map((n) => ({ categoria: n.categoria, data: n.data, valor: n.valor })),
        semCategoria ? 0 : (limiteDia ?? Number(cadastros?.limite_refeicao_dia ?? 0)),
        Number(cadastros?.limite_solicitacao ?? 0),
        categoriasRefeicao
      ),
    [notas, cadastros, semCategoria, limiteDia, categoriasRefeicao]
  )

  function mudarNota(chave: number, mudanca: Partial<NotaForm>) {
    setNotas((atual) => atual.map((n) => (n.chave === chave ? { ...n, ...mudanca } : n)))
  }

  function removerNota(chave: number) {
    setNotas((atual) => atual.filter((n) => n.chave !== chave))
  }

  return (
    <>
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
              {!semCategoria && (
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
              )}
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
                Descrição {n.categoria === DESCRICAO_OBRIGATORIA ? '' : '(opcional)'}
              </label>
              <input
                id={`desc-${n.chave}`}
                value={n.descricao}
                maxLength={200}
                placeholder={n.categoria === DESCRICAO_OBRIGATORIA ? 'Ex.: Cópias de documentos' : ''}
                onChange={(e) => mudarNota(n.chave, { descricao: e.target.value })}
                required={n.categoria === DESCRICAO_OBRIGATORIA}
              />
            </div>
            <div className={`${ui.campo} ${styles.anexo}`}>
              <label htmlFor={`arq-${n.chave}`}>
                <Icone nome="camera" tamanho={20} />
                {n.id ? 'Trocar a nota (opcional)' : 'Foto ou PDF da nota'}
              </label>
              <input
                id={`arq-${n.chave}`}
                type="file"
                accept={ACEITOS}
                onChange={(e) => mudarNota(n.chave, { arquivo: e.target.files?.[0] ?? null })}
              />
              {n.arquivo && <Miniatura arquivo={n.arquivo} />}
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
          <Icone nome="mais" tamanho={18} />
          Adicionar nota
        </button>
        <span className={styles.total}>
          <span>Total</span> {formatarMoeda(total)}
        </span>
      </div>
      <span className={ui.ajuda}>JPG, PNG ou PDF, até 10 MB cada. No celular, dá para tirar a foto na hora.</span>

      {alertas.map((a) => (
        <div key={a} className={`${ui.aviso} ${styles.alerta}`}>
          <Icone nome="alerta" tamanho={20} />
          <span>{a} Você pode enviar mesmo assim — o financeiro vai ver o alerta.</span>
        </div>
      ))}
    </>
  )
}
