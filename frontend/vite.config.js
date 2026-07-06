import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev proxy target for /api — override with BACKEND_URL when the backend
// runs on a non-default port (e.g. 8055 on machines where 8000 is taken).
const backend = process.env.BACKEND_URL || 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    // PORT override for machines where 3000 is taken; strictPort avoids
    // silently half-binding to [::1] when IPv4:3000 is occupied, and
    // host:true binds IPv4+IPv6 so both localhost resolutions work.
    host: true,
    port: Number(process.env.PORT) || 3000,
    strictPort: true,
    proxy: {
      '/api': { target: backend, changeOrigin: true },
    },
  },
});
