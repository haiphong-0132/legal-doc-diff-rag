import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    allowedHosts: ['ben-overall-arlington-establishment.trycloudflare.com'],
    proxy: {
      '/api': {
        target: 'https://previews-clear-brakes-transmission.trycloudflare.com',
        changeOrigin: true,
      },
    },
  },
})
