import { Router } from 'express';
import * as ibkr from '../lib/ibkrClient.js';

const router = Router();

// Check IBKR gateway connection status
router.get('/ibkr/status', async (req, res) => {
  try {
    const status = await ibkr.getAuthStatus();
    res.json({ success: true, ...status });
  } catch (e: any) {
    res.json({ success: false, authenticated: false, connected: false, error: e.message });
  }
});

// Get account summary
router.get('/ibkr/account', async (req, res) => {
  try {
    const summary = await ibkr.getAccountSummary(req.query.accountId as string);
    res.json({ success: true, data: summary });
  } catch (e: any) {
    res.status(500).json({ success: false, error: e.message });
  }
});

// Get all accounts
router.get('/ibkr/accounts', async (req, res) => {
  try {
    const accounts = await ibkr.getAccounts();
    res.json({ success: true, data: accounts });
  } catch (e: any) {
    res.status(500).json({ success: false, error: e.message });
  }
});

// Get current positions with P&L
router.get('/ibkr/positions', async (req, res) => {
  try {
    const positions = await ibkr.getPositions(req.query.accountId as string);
    res.json({ success: true, data: positions });
  } catch (e: any) {
    res.status(500).json({ success: false, error: e.message });
  }
});

// Get real-time P&L (daily)
router.get('/ibkr/pnl', async (req, res) => {
  try {
    const pnl = await ibkr.getPnL();
    res.json({ success: true, data: pnl });
  } catch (e: any) {
    res.status(500).json({ success: false, error: e.message });
  }
});

// Get monthly performance data
router.get('/ibkr/performance', async (req, res) => {
  try {
    const period = (req.query.period as string) || '12M';
    const perf = await ibkr.getPerformance(req.query.accountId as string, period);
    res.json({ success: true, data: perf });
  } catch (e: any) {
    res.status(500).json({ success: false, error: e.message });
  }
});

// Get transactions history
router.get('/ibkr/transactions', async (req, res) => {
  try {
    const days = parseInt(req.query.days as string) || 30;
    const data = await ibkr.getTransactions(req.query.accountId as string, days);
    res.json({ success: true, data });
  } catch (e: any) {
    res.status(500).json({ success: false, error: e.message });
  }
});

// Get daily P&L for a specific position (by conid)
router.get('/ibkr/pnl/daily/:conid', async (req, res) => {
  try {
    const conid = parseInt(req.params.conid);
    if (isNaN(conid)) {
      return res.status(400).json({ success: false, error: 'Invalid conid' });
    }
    const data = await ibkr.getDailyPnL(conid);
    res.json({ success: true, data });
  } catch (e: any) {
    res.status(500).json({ success: false, error: e.message });
  }
});

// Search for a contract by symbol
router.get('/ibkr/search/:symbol', async (req, res) => {
  try {
    const symbol = req.params.symbol;
    if (!symbol || symbol.length > 20) {
      return res.status(400).json({ success: false, error: 'Invalid symbol' });
    }
    const data = await ibkr.searchContract(symbol);
    res.json({ success: true, data });
  } catch (e: any) {
    res.status(500).json({ success: false, error: e.message });
  }
});

// Get option strikes for a contract
router.post('/ibkr/options/strikes', async (req, res) => {
  try {
    const { conid, secType, month, exchange } = req.body;
    if (!conid || !month) {
      return res.status(400).json({ success: false, error: 'conid and month required' });
    }
    const data = await ibkr.getOptionStrikes(conid, secType || 'OPT', month, exchange);
    res.json({ success: true, data });
  } catch (e: any) {
    res.status(500).json({ success: false, error: e.message });
  }
});

// Get option chain info
router.post('/ibkr/options/chain', async (req, res) => {
  try {
    const { conid, secType, month, strike, right } = req.body;
    if (!conid) {
      return res.status(400).json({ success: false, error: 'conid required' });
    }
    const data = await ibkr.getOptionChain(conid, secType, month, strike, right);
    res.json({ success: true, data });
  } catch (e: any) {
    res.status(500).json({ success: false, error: e.message });
  }
});

// Get market data history (K-line)
router.get('/ibkr/history/:conid', async (req, res) => {
  try {
    const conid = parseInt(req.params.conid);
    if (isNaN(conid)) {
      return res.status(400).json({ success: false, error: 'Invalid conid' });
    }
    const period = (req.query.period as string) || '1Y';
    const bar = (req.query.bar as string) || '1d';
    const data = await ibkr.getMarketDataHistory(conid, period, bar);
    res.json({ success: true, data });
  } catch (e: any) {
    res.status(500).json({ success: false, error: e.message });
  }
});

export default router;
