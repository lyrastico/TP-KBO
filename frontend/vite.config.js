import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Le backend FastAPI tourne sur :8000. On proxifie /api pour rester en same-origin
// (pas de CORS en dev) et pouvoir déployer derrière un même reverse-proxy en prod.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 127.0.0.1 explicite : uvicorn n'écoute qu'en IPv4, alors que 'localhost'
      // se résout d'abord en IPv6 (::1) côté Node -> connexion refusée.
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
