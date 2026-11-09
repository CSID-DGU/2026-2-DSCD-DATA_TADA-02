import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000', '/health': 'http://127.0.0.1:8000' } },
  // This Windows Node runtime exits natively when Vite empties an existing dist.
  // Keep hashed development assets; the clean Linux Docker build still empties its output.
  build: { emptyOutDir: process.platform !== 'win32', sourcemap: false, rollupOptions: { output: { manualChunks: {
    charts: ['recharts'], map: ['leaflet'],
  } } } },
});
