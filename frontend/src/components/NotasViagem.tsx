import { useMemo, type Dispatch, type SetStateAction } from 'react'
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
}

// Lista de notas de viagem (categoria, data, valor, descrição e arquivo), com
// total e alertas da política. Usada no reembolso de viagem e na prestação de
// contas do adiantamento.
export default function NotasViagem({ notas, setNotas, cadastros }: Props) {
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
    </>
  )
}
