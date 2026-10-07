/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],

  resolve: {
    alias: {
      '@': resolve(__dirname, './src'),
    },
  },

  server: {
    port: 5173,
    // Proxy para o backend durante desenvolvimento local
    // Assim as chamadas para /api/* vão para o backend sem CORS
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8081',
        changeOrigin: true,
      },
    },
  },

  test: {
    environment: 'jsdom',
  },

  build: {
    outDir: 'dist',
    sourcemap: false,
    // Divide o bundle por módulo para melhor performance de cache.
    // Vite 8 usa Rolldown: `rollupOptions` virou `rolldownOptions` e o
    // `manualChunks` em formato de objeto foi trocado por `codeSplitting.groups`.
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: 'react', test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/ },
            { name: 'router', test: /node_modules[\\/](react-router|react-router-dom|@remix-run)[\\/]/ },
          ],
        },
      },
    },
  },
})
