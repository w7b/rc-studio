import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [tailwindcss()],
  build: { outDir: 'dist', emptyOutDir: true },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
        configure(proxy) {
          proxy.on('proxyReq', (req) => req.setHeader('Origin', 'http://127.0.0.1:8765'));
        },
      },
      '/media': { target: 'http://127.0.0.1:8765', changeOrigin: true },
    },
  },
});
