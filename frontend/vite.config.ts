import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    exclude: ['mermaid'],
    include: ['dayjs', '@braintree/sanitize-url']
  },
  resolve: {
    alias: {
      'dayjs': 'dayjs/dayjs.min.js',
      '@braintree/sanitize-url': path.resolve(__dirname, 'node_modules/@braintree/sanitize-url/dist/index.mjs')
    }
  }
})
