import { useEffect, useState } from 'react'
import { precisaDosDados, type BeneficiarioForm } from '@/beneficiario'
import { api } from '@/services/api'
import ui from '@/styles/ui.module.css'
import type { Opcao, UsuarioBusca } from '@/types'

interface Props {
  valor: BeneficiarioForm
  onChange: (valor: BeneficiarioForm) => void
  centros: Opcao[]
}

// "Pedir em nome de outra pessoa": busca entre os colegas que já entraram no
// sistema; se a pessoa nunca entrou, pede nome, matrícula e centro de custo.
export default function BeneficiarioCampos({ valor, onChange, centros }: Props) {
  const [sugestoes, setSugestoes] = useState<UsuarioBusca[]>([])
  const termo = valor.email.trim()

  useEffect(() => {
    if (!valor.ativo || termo.length < 2) {
      setSugestoes([])
      return
    }
    const espera = setTimeout(() => {
      api
        .get<UsuarioBusca[]>('/api/usuarios', { params: { busca: termo } })
        .then((r) => setSugestoes(r.data))
        .catch(() => setSugestoes([]))
    }, 300)
    return () => clearTimeout(espera)
  }, [valor.ativo, termo])

  function mudarEmail(texto: string) {
    const conhecido = sugestoes.find((u) => u.email === texto.trim().toLowerCase()) ?? null
    onChange({ ...valor, email: texto, conhecido })
  }

  // A sugestão pode chegar depois do texto digitado: liga o colega achado.
  useEffect(() => {
    if (!valor.ativo || valor.conhecido) return
    const achado = sugestoes.find((u) => u.email === termo.toLowerCase())
    if (achado) onChange({ ...valor, conhecido: achado })
  }, [sugestoes, termo, valor, onChange])

  return (
    <div className={ui.campo}>
      <label style={{ fontWeight: 400 }}>
        <input
          type="checkbox"
          checked={valor.ativo}
          onChange={(e) => onChange({ ...valor, ativo: e.target.checked })}
        />{' '}
        Pedir em nome de outra pessoa
      </label>
      {valor.ativo && (
        <>
          <span className={ui.ajuda}>
            O reembolso vai para essa pessoa, e quem aprova é o gestor dela.
          </span>
          <label htmlFor="beneficiarioEmail">E-mail da pessoa</label>
          <input
            id="beneficiarioEmail"
            type="email"
            list="beneficiarioSugestoes"
            placeholder="Digite o nome ou o e-mail"
            value={valor.email}
            maxLength={254}
            onChange={(e) => mudarEmail(e.target.value)}
            required
          />
          <datalist id="beneficiarioSugestoes">
            {sugestoes.map((u) => (
              <option key={u.email} value={u.email}>
                {u.nome}
              </option>
            ))}
          </datalist>
          {valor.conhecido?.perfil_completo && (
            <span className={ui.ajuda}>
              {valor.conhecido.nome}: os dados (matrícula e centro de custo) vêm do perfil dela.
            </span>
          )}
          {precisaDosDados(valor) && termo.includes('@') && (
            <>
              <span className={ui.ajuda}>
                Essa pessoa ainda não entrou no sistema: preencha os dados dela.
              </span>
              <div className={ui.grade}>
                <div className={ui.campo}>
                  <label htmlFor="beneficiarioNome">Nome</label>
                  <input
                    id="beneficiarioNome"
                    value={valor.nome}
                    maxLength={200}
                    onChange={(e) => onChange({ ...valor, nome: e.target.value })}
                    required
                  />
                </div>
                <div className={ui.campo}>
                  <label htmlFor="beneficiarioMatricula">Matrícula</label>
                  <input
                    id="beneficiarioMatricula"
                    value={valor.matricula}
                    maxLength={30}
                    onChange={(e) => onChange({ ...valor, matricula: e.target.value })}
                    required
                  />
                </div>
              </div>
              <div className={ui.campo}>
                <label htmlFor="beneficiarioCentro">Centro de custo dela</label>
                <select
                  id="beneficiarioCentro"
                  value={valor.centroCustoId}
                  onChange={(e) => onChange({ ...valor, centroCustoId: e.target.value })}
                  required
                >
                  <option value="">Selecione…</option>
                  {centros.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.rotulo}
                    </option>
                  ))}
                </select>
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
