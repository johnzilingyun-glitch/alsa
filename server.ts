import express from 'express';
import { createServer as createViteServer } from 'vite';
import path from 'path';
import { fileURLToPath } from 'url';
import dotenv from 'dotenv';
import { createProxyMiddleware } from 'http-proxy-middleware';

import historyRoutes, { addLogEntry } from './server/historyRoutes.js';
import feishuRoutes from './server/feishuRoutes.js';
import stockRoutes from './server/stockRoutes.js';
import debugRoutes from './server/debugRoutes.js';
import analysisRoutes from './server/routes/analysisRoutes.js';
import { monitor } from './server/dataSourceHealth.js';

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function startServer() {
  const app = express();
  const PORT = 3000;

  app.use(express.json({ limit: '2mb' }));
  app.use(express.urlencoded({ limit: '2mb', extended: true }));

  // Security headers
  app.use((req, res, next) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('X-Frame-Options', 'DENY');
    res.setHeader('X-XSS-Protection', '1; mode=block');
    res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
    next();
  });
  
  app.get('/api/ping-early', (req, res) => {
    res.json({ ok: true, msg: 'Absolute earliest route' });
  });

  // API routes FIRST
  app.get('/api/health', (req, res) => {
    console.log('Health check called');
    res.json({
      success: true,
      status: 'ok',
      service: 'Node API Gateway',
      message: 'Node API gateway is running',
    });
  });

  app.get('/api/health/data-sources', (req, res) => {
    console.log('Data sources health check called');
    res.json(monitor.getHealthReport());
  });

  // Route modules
  console.log('Mounting API routes...');
  
  app.use('/api/diagnostics', debugRoutes);
  console.log('Registered: /api/diagnostics/logs/debug');

  app.get('/api/ping-debug', (req, res) => {
    res.json({ ok: true, msg: 'Direct route check works' });
  });

  app.use('/api', (req, res, next) => {
    console.log(`API Request: ${req.method} ${req.url}`);
    next();
  }, historyRoutes);
  app.use('/api', feishuRoutes);
  app.use('/api', stockRoutes);
  app.use('/api', analysisRoutes);

  // Proxy to FastAPI for new routes (or all handled by FastAPI later)
  // This will handle /api/analysis/ jobs and others once they are moved to Python
  app.use('/api', createProxyMiddleware({ 
    target: 'http://127.0.0.1:8001', 
    changeOrigin: true,
    pathFilter: (path) => {
      // Proxy if not handled by existing routes or if explicitly for analytics/market/journal/watchlist
      return path.match(/^\/api\/(analysis|market|journal|watchlist)/) !== null;
    }
  }));

  // Handle 404 for API routes explicitly to avoid falling through to SPA
  app.all('/api/*', (req, res) => {
    console.warn(`API 404: ${req.method} ${req.originalUrl}`);
    res.status(404).json({ error: `API route ${req.originalUrl} not found` });
  });

  // Vite middleware for development
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      root: process.cwd(),
      server: { 
        middlewareMode: true,
        hmr: { port: 0 } 
      },
      appType: 'spa',
    });
    app.use(vite.middlewares);
    // SPA fallback for development mode
    app.get('*', (req, res) => {
      res.redirect('/');
    });
  }

  // Production serving
  if (process.env.NODE_ENV === 'production') {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  const server = app.listen(PORT, '0.0.0.0', () => {
    console.log(`Server running on http://localhost:${PORT}`);
    console.log(`GEMINI_API_KEY configured: ${!!process.env.GEMINI_API_KEY}`);
    addLogEntry('server', 'startup', 'active', 'Server started and background tasks initialized');
  });

  server.on('error', (e: any) => {
    if (e.code === 'EADDRINUSE') {
      console.error(`Port ${PORT} is already in use. Please wait or restart the dev server.`);
    } else {
      console.error('Server error:', e);
    }
  });
}

startServer();
