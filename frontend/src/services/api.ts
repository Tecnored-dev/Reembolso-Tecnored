import axios from 'axios'

// ---------------------------------------------------------------------------
// Cliente HTTP (mesmo padrão do Hello-World)
//
// withCredentials é OBRIGATÓRIO: é o que faz o navegador mandar o cookie
// httponly de sessão nas chamadas cross-origin para a API.
// ---------------------------------------------------------------------------
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '',
  timeout: 20_000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

// Rotas de navegação de página inteira (fluxo OAuth) — <a href>, nunca axios.
const API_URL = import.meta.env.VITE_API_URL ?? ''
export const LOGIN_URL = `${API_URL}/login`
export const LOGOUT_URL = `${API_URL}/logout`
export const DEV_LOGIN_URL = `${API_URL}/dev/login`
