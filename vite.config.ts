import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default defineConfig(() => {
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
      minify: 'esbuild' as const,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes('node_modules')) return undefined;
            if (id.includes('react-markdown') || id.includes('remark-') || id.includes('rehype-')) return 'vendor-markdown';
            if (id.includes('motion') || id.includes('framer-motion')) return 'vendor-motion';
            if (id.includes('lucide-react')) return 'vendor-icons';
            if (id.includes('recharts') || id.includes('d3-')) return 'vendor-charts';
            if (id.includes('lightweight-charts')) return 'vendor-lightweight-charts';
            if (id.includes('@google/genai')) return 'vendor-genai';
            if (id.includes('i18next') || id.includes('react-i18next')) return 'vendor-i18n';
            if (id.includes('zod')) return 'vendor-schema';
            if (id.includes('react') || id.includes('scheduler')) return undefined;
            return 'vendor-misc';
          },
        },
      },
    },
    server: {
      host: true,
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
        ignored: ['**/.venv/**', '**/.venv_qlib/**', '**/node_modules/**', '**/data/**', '**/python_service/**', '**/server/**', '**/server.ts', '**/scratch/**', '**/logs/**', '**/docs/**', '**/sector_reports/**', '**/reports/**', '**/*.log', '**/*.db', '**/*.db-journal', '**/PaperTrading_System/**', '**/.mimocode/**'],
      },
    },
    preview: {
      host: true,
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
    },
  };
});
