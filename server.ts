import { Server } from 'socket.io';
import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';
import dotenv from 'dotenv';
import { createProxyMiddleware } from 'http-proxy-middleware';

import historyRoutes, { addLogEntry } from './server/historyRoutes.js';
import feishuRoutes from './server/feishuRoutes.js';
import stockRoutes from './server/stockRoutes.js';
import debugRoutes from './server/debugRoutes.js';
import analysisRoutes from './server/routes/analysisRoutes.js';
import ibkrRoutes from './server/routes/ibkrRoutes.js';
import llmRoutes from './server/routes/llmRoutes.js';
import { monitor } from './server/dataSourceHealth.js';
import { buildSocketCorsOptions, getServerHost, getServerPort, isDiagnosticsEnabled, shouldBypassGatewayApiToken, shouldRequireApiToken, validateApiToken, validateSocketToken } from './server/securityConfig.js';
import { applySecurityHeaders } from './server/securityHeaders.js';
import { createRateLimiter } from './server/rateLimiter.js';
import { formatHttpLog } from './server/logSanitizer.js';

dotenv.config();
dotenv.config({ path: '.env.runtime' });

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function startServer() {
  const app = express();
  const PORT = getServerPort();
  const HOST = getServerHost();

  app.use(express.json({ limit: '2mb' }));
  app.use(express.urlencoded({ limit: '2mb', extended: true }));

  app.use(applySecurityHeaders);
  app.use('/api', createRateLimiter());
  
  // Performance logging middleware
  app.use((req, res, next) => {
    const start = Date.now();
    res.on('finish', () => {
      const duration = Date.now() - start;
      if (duration > 500) { // Only log slow requests
        console.log(`[PERF] ${formatHttpLog(req.method, req.originalUrl, res.locals.requestId, duration)}`);
      }
    });
    next();
  });

  app.get('/api/ping-early', (req, res) => {
    res.json({ ok: true, msg: 'Absolute earliest route' });
  });

  if (shouldRequireApiToken()) {
    app.use('/api', (req, res, next) => {
      if (shouldBypassGatewayApiToken(req.path)) return next();
      if (!validateApiToken(req.header('authorization'))) {
        return res.status(401).json({ success: false, error: 'Unauthorized' });
      }
      next();
    });
  }

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
  
  if (isDiagnosticsEnabled()) {
    app.use('/api/diagnostics', debugRoutes);
    console.log('Registered: /api/diagnostics/logs/debug');
  } else {
    console.log('Diagnostics routes disabled. Set ENABLE_DIAGNOSTICS=true to enable them.');
  }

  if (isDiagnosticsEnabled()) {
    app.get('/api/ping-debug', (req, res) => {
      res.json({ ok: true, msg: 'Direct route check works' });
    });
  }

  app.use('/api', (req, res, next) => {
    console.log(`API Request: ${formatHttpLog(req.method, req.url, res.locals.requestId)}`);
    next();
  }, historyRoutes);
  app.use('/api', feishuRoutes);
  app.use('/api', analysisRoutes);
  app.use('/api', ibkrRoutes);
  app.use('/api', stockRoutes);
  app.use('/api', llmRoutes);
  app.use('/api/v1', historyRoutes);
  app.use('/api/v1', feishuRoutes);
  app.use('/api/v1', analysisRoutes);
  app.use('/api/v1', ibkrRoutes);
  app.use('/api/v1', stockRoutes);
  app.use('/api/v1', llmRoutes);

  // Proxy to FastAPI (Port 8001 or PYTHON_BACKEND_URL) for paths not handled by Node
  app.use(createProxyMiddleware({ 
    target: process.env.PYTHON_BACKEND_URL || 'http://127.0.0.1:8001', 
    changeOrigin: true,
    pathFilter: (path) => {
      const targets = [
        '/api/brain', 
        '/api/evolution', 
        '/api/market', 
        '/api/journal', 
        '/api/watchlist', 
        '/api/alerts',
        '/api/analysis',
        '/api/sector',
        '/api/mock-trading',
        '/api/ths',
        '/api/backtest',
        '/api/auth',
        '/api/admin',
        '/api/predictions',
        '/api/technicals',
        '/api/screening',
        '/api/stock',
        '/api/v1/brain',
        '/api/v1/evolution',
        '/api/v1/market',
        '/api/v1/journal',
        '/api/v1/watchlist',
        '/api/v1/alerts',
        '/api/v1/analysis',
        '/api/v1/sector',
        '/api/v1/mock-trading',
        '/api/v1/trade-intents',
        '/api/v1/backtest',
        '/api/v1/predictions'
      ];
      return targets.some(t => path.startsWith(t));
    },
    on: {
      proxyReq: (proxyReq, req: any) => {
        // Inject API_TOKEN for Python service auth (skip auth routes — they use user JWT)
        const isAuthRoute = req.path.includes('/auth') || req.originalUrl.includes('/auth');
        if (!isAuthRoute) {
          const pyToken = process.env.API_TOKEN;
          if (pyToken) {
            proxyReq.setHeader('Authorization', `Bearer ${pyToken}`);
          }
        }
        // Inject ADMIN_TOKEN for admin routes
        const isAdminRoute = req.path.includes('/admin') || req.originalUrl.includes('/admin');
        if (isAdminRoute) {
          const adminToken = process.env.ADMIN_TOKEN;
          if (adminToken) {
            proxyReq.setHeader('x-admin-token', adminToken);
          }
        }
        // express body parsers consume the stream before proxy can forward it.
        // Re-serialize req.body in the original content type.
        if (req.body && ['POST', 'PUT', 'PATCH'].includes(req.method)) {
          const originalCT = req.headers['content-type'] || '';
          let bodyData: string;
          if (originalCT.includes('application/x-www-form-urlencoded')) {
            bodyData = new URLSearchParams(req.body).toString();
            proxyReq.setHeader('Content-Type', 'application/x-www-form-urlencoded');
          } else {
            bodyData = JSON.stringify(req.body);
            proxyReq.setHeader('Content-Type', 'application/json');
          }
          proxyReq.setHeader('Content-Length', Buffer.byteLength(bodyData).toString());
          proxyReq.write(bodyData);
        }
      }
    }
  }));

  // Handle 404 for API routes explicitly to avoid falling through to SPA
  app.all('/api/*', (req, res) => {
    console.warn(`API 404: ${req.method} ${req.originalUrl}`);
    res.status(404).json({ error: `API route ${req.originalUrl} not found` });
  });

  // Production serving
  if (process.env.NODE_ENV === 'production') {
    const distPath = path.join(__dirname, 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  } else {
    // Dev mode: redirect root to Vite dev server
    app.get('/', (req, res) => {
      res.redirect('http://localhost:5173/');
    });
  }

  // Start HTTP listener
  const server = app.listen(PORT, HOST, () => {
    console.log(`Server running on http://${HOST}:${PORT}`);
    console.log(`GEMINI_API_KEY configured: ${!!process.env.GEMINI_API_KEY}`);
    addLogEntry('server', 'startup', 'active', 'Server started and background tasks initialized');
  });

  const io = new Server(server, { cors: buildSocketCorsOptions() });
  app.set('io', io);

  io.use((socket, next) => {
    const authToken = typeof socket.handshake.auth?.token === 'string' ? socket.handshake.auth.token : undefined;
    const queryToken = typeof socket.handshake.query?.token === 'string' ? socket.handshake.query.token : undefined;
    if (validateSocketToken(authToken || queryToken)) return next();
    next(new Error('Unauthorized'));
  });

  io.on('connection', (socket) => {
    console.log('Client connected:', socket.id);
    socket.on('joinRoom', (room) => {
      socket.join(room);
      console.log(`Socket ${socket.id} joined room: ${room}`);
    });
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
