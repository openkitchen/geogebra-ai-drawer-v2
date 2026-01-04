import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

function toPort(value: string | undefined, fallback: number) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

export default defineConfig(() => {
  const webHost = process.env.WEB_HOST || '127.0.0.1';
  const webPort = toPort(process.env.WEB_PORT, 3000);

  const apiHost = process.env.API_HOST || '127.0.0.1';
  const apiPort = toPort(process.env.API_PORT, 3002);
  const apiTarget = `http://${apiHost}:${apiPort}`;

  return {
    plugins: [react()],
    server: {
      host: webHost,
      port: webPort,
      strictPort: true,
      proxy: {
        '/api': apiTarget,
        '/healthz': apiTarget,
      },
    },
  };
});
