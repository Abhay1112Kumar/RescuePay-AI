import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Local development routing only. The production host must route /api separately.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: process.env.RESCUEPAY_API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
        timeout: 6000,
        proxyTimeout: 6000,
      },
    },
  },
})
