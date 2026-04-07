import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    allowedHosts: ['outputs-closes-sen-creates.trycloudflare.com'],
    proxy: {
      '/api': {
        target: 'https://damaged-features-differently-personally.trycloudflare.com',
        changeOrigin: true,
        secure: true,
      },
    },
  },
})
