import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: '0.0.0.0', // Allow access from Docker network
    allowedHosts: [
      'localhost',
      '.localhost', // Allow all localhost subdomains
      'udayachal-ai.local',
      '.local', // Allow all .local domains
      'zoria.krishnabihari.com',
      '.krishnabihari.com', // Allow all krishnabihari.com subdomains
    ],
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true
      }
    }
  }
})
