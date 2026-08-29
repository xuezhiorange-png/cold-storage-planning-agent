import path from 'node:path'
import { fileURLToPath } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@v09-operator-demo': path.join(repoRoot, 'samples/v09-process-input/manifest.json')
    }
  },
  server: {
    host: '0.0.0.0',
    fs: {
      allow: [repoRoot]
    },
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000'
    }
  },
  test: {
    environment: 'jsdom',
    testTimeout: 30000,
    hookTimeout: 30000
  }
})
