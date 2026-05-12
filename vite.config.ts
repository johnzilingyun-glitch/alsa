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
        'motion/react', 'lucide-react', 
        'react-i18next', 'i18next', 'i18next-browser-languagedetector',
        'clsx', 'tailwind-merge',
        'zustand', 'zustand/middleware',
        '@google/genai',
      ],
    },
    build: {
      target: 'esnext',
      minify: 'esbuild',
    },
    server: {
      hmr: {
        port: 0,
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
