import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    include: ['src/test/**/*.test.ts'],
    environment: 'node',
    exclude: ['node_modules', 'node_modules.bak', 'dist', 'e2e'],
    coverage: {
      enabled: false,
    },
  },
})
