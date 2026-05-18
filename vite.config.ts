import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  return {
    plugins: [react(), tailwindcss()],
    optimizeDeps: {
      include: [
        'react', 'react-dom', 'react-dom/client',
        'motion/react', 'framer-motion', 'lucide-react',
        'react-i18next', 'i18next', 'i18next-browser-languagedetector',
        'clsx', 'tailwind-merge',
        'zustand', 'zustand/middleware',
        '@google/genai',
        'react-markdown', 'remark-gfm', 'rehype-raw',
        'recharts',
        'socket.io-client',
      ],
    },
    build: {
      target: 'esnext',
      minify: 'esbuild',
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: 'http://localhost:3000',
          changeOrigin: true,
        },
        '/socket.io': {
          target: 'http://localhost:3000',
          ws: true,
        },
      },
      warmup: {
        clientFiles: ['./src/main.tsx', './src/App.tsx', './src/i18n/index.ts'],
      },
      watch: {
        ignored: ['**/data/**', '**/python_service/**', '**/server/**', '**/server.ts', '**/scratch/**', '**/logs/**', '**/docs/**'],
      },
    },
    define: {
      'process.env.GEMINI_API_KEY': JSON.stringify(env.GEMINI_API_KEY || ''),
      'process.env.DEEPSEEK_API_KEY': JSON.stringify(env.DEEPSEEK_API_KEY || ''),
    },
  };
});
