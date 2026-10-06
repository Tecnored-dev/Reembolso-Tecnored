/// <reference types="vite/client" />

// Declaração das variáveis de ambiente disponíveis via import.meta.env
// Adicione aqui novas VITE_ vars conforme o projeto crescer
interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_APP_ENV: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
