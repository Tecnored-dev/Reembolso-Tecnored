import type { ReactNode } from 'react'

// Ícones de traço do design system (24×24, traço 2, cor herdada do texto).
// Desenhos inline para não depender de biblioteca. Decorativos: botão só com
// ícone precisa de aria-label no próprio botão.
const DESENHOS = {
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  x: <path d="M6 6l12 12M18 6L6 18" />,
  lupa: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M16 16l4.5 4.5" />
    </>
  ),
  pessoa: (
    <>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5 20c1-4 4-5.5 7-5.5s6 1.5 7 5.5" />
    </>
  ),
  cifrao: (
    <path d="M12 3v18M16.5 7.5c-.6-1.6-2.3-2.5-4.5-2.5-2.6 0-4.5 1.3-4.5 3.3 0 4.7 9 2.4 9 7.2 0 2-2 3.5-4.6 3.5-2.4 0-4.2-1-4.9-2.8" />
  ),
  relogio: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  'seta-volta': <path d="M9 14L4 9l5-5M4 9h10.5a5.5 5.5 0 010 11H11" />,
  recibo: <path d="M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6M9 16h3" />,
  carteira: <path d="M4 7h15a1 1 0 011 1v11a1 1 0 01-1 1H5a1 1 0 01-1-1zM4 7l11-3v3M15.5 13.5h.01" />,
  camera: (
    <>
      <path d="M4 8h3l2-3h6l2 3h3v11H4z" />
      <circle cx="12" cy="13.5" r="3.5" />
    </>
  ),
  alerta: <path d="M12 4l9 16H3zM12 10v4.5M12 17.5v.01" />,
  info: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11v5.5M12 7.8v.01" />
    </>
  ),
  mais: <path d="M12 5v14M5 12h14" />,
  talher: <path d="M7 3v18M4.5 3v5a2.5 2.5 0 005 0V3M17 21V3c-2 0-3.5 2.5-3.5 6s1.5 4 3.5 4" />,
  mala: (
    <>
      <rect x="3.5" y="7" width="17" height="13" rx="2" />
      <path d="M9 7V4.5h6V7M3.5 12.5h17" />
    </>
  ),
  caixa: <path d="M4 8l8-4 8 4v9l-8 4-8-4zM4 8l8 4 8-4M12 12v9" />,
  sair: <path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10" />,
} satisfies Record<string, ReactNode>

export type NomeIcone = keyof typeof DESENHOS

// Tamanhos do design system: 20 em texto, 18 em botão, 15 em selo, 22 no cartão.
export default function Icone({
  nome,
  tamanho = 20,
  className,
}: {
  nome: NomeIcone
  tamanho?: number
  className?: string
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={tamanho}
      height={tamanho}
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
      style={{ flex: 'none' }}
    >
      {DESENHOS[nome]}
    </svg>
  )
}
