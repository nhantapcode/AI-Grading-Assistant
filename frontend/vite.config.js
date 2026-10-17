import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: { environment: 'jsdom', setupFiles: './src/test-setup.js', include: ['src/**/*.test.jsx'] },
  server: { port: 5173, strictPort: true, proxy: { '/api': process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000' } },
});
