import { Router } from 'express';
import fs from 'fs';
import path from 'path';

const HISTORY_DIR = path.join(process.cwd(), 'data', 'history');
const LOG_FILE = path.join(process.cwd(), 'data', 'optimization_log.json');

const RETENTION_DAYS = 30;

// Ensure directories exist
if (!fs.existsSync(path.join(process.cwd(), 'data'))) {
  fs.mkdirSync(path.join(process.cwd(), 'data'));
}
if (!fs.existsSync(HISTORY_DIR)) {
  fs.mkdirSync(HISTORY_DIR);
}
if (!fs.existsSync(LOG_FILE)) {
  fs.writeFileSync(LOG_FILE, JSON.stringify([], null, 2));
}

// Cleanup history files older than RETENTION_DAYS on startup
function cleanupOldHistory() {
  try {
    const cutoff = Date.now() - RETENTION_DAYS * 24 * 60 * 60 * 1000;
    const files = fs.readdirSync(HISTORY_DIR);
    let deleted = 0;
    for (const f of files) {
      // Extract ISO timestamp from filename: type_YYYY-MM-DDTHH-MM-SS-mmmZ_id.json
      const match = f.match(/^\w+_(\d{4}-\d{2}-\d{2}T[\d-]+Z)/);
      if (match) {
        const isoStr = match[1]
          .replace(/T(\d{2})-(\d{2})-(\d{2})/, 'T$1:$2:$3')
          .replace(/-(\d{3})Z$/, '.$1Z');
        const fileDate = new Date(isoStr);
        if (!isNaN(fileDate.getTime()) && fileDate.getTime() < cutoff) {
          fs.unlinkSync(path.join(HISTORY_DIR, f));
          deleted++;
        }
      }
    }
    if (deleted > 0) {
      console.log(`[History Cleanup] Deleted ${deleted} files older than ${RETENTION_DAYS} days.`);
    }
  } catch (err) {
    console.error('[History Cleanup] Error:', err);
  }
}

cleanupOldHistory();

export function addLogEntry(field: string, oldValue: any, newValue: any, description: string) {
  try {
    const logs = JSON.parse(fs.readFileSync(LOG_FILE, 'utf-8'));
    logs.push({
      timestamp: new Date().toISOString(),
      field,
      oldValue,
      newValue,
      description
    });
    fs.writeFileSync(LOG_FILE, JSON.stringify(logs, null, 2));
  } catch (err) {
    console.error('Failed to add log entry:', err);
  }
}

function saveAnalysis(type: 'market' | 'stock', data: any) {
  const now = Date.now();
  const id = `${type}-${now}-${Math.random().toString(36).substr(2, 9)}`;
  // Ensure the object has type, id, and generatedAt for easier frontend recovery
  const dataToSave = { 
    ...data, 
    id, 
    type,
    generatedAt: data.generatedAt || now 
  };
  
  const filename = `${type}_${new Date().toISOString().replace(/[:.]/g, '-')}_${Math.random().toString(36).substr(2, 5)}.json`;
  const filePath = path.join(HISTORY_DIR, filename);
  fs.writeFileSync(filePath, JSON.stringify(dataToSave, null, 2));
  console.log(`[History] Saved ${type} analysis. ID: ${id}, Filename: ${filename}`);
}

const router = Router();

router.get('/history/context', (req, res) => {
  console.log('GET /api/history/context called');
  try {
    const files = fs.readdirSync(HISTORY_DIR).sort().reverse().slice(0, 100);
    const history = files.map(f => {
      try {
        return JSON.parse(fs.readFileSync(path.join(HISTORY_DIR, f), 'utf-8'));
      } catch (err) {
        console.error(`Failed to parse history file ${f}:`, err);
        return null;
      }
    }).filter(h => h !== null);
    res.json(history);
  } catch (err) {
    console.error('Failed to read history:', err);
    res.status(500).json({ error: 'Failed to read history' });
  }
});

// Helper: extract Beijing date from a history file's data or filename
function extractBeijingDate(data: any, filename: string): string | null {
  if (data.generatedAt) {
    const genDate = new Date(data.generatedAt);
    if (!isNaN(genDate.getTime())) {
      return genDate.toLocaleDateString('en-CA', { timeZone: 'Asia/Shanghai' });
    }
  }
  // Fallback: parse ISO timestamp from filename (e.g. market_2026-04-07T09-02-29-582Z_xxx.json)
  const match = filename.match(/^\w+_(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})-(\d{3})Z/);
  if (match) {
    const isoStr = `${match[1]}T${match[2]}:${match[3]}:${match[4]}.${match[5]}Z`;
    const d = new Date(isoStr);
    if (!isNaN(d.getTime())) {
      return d.toLocaleDateString('en-CA', { timeZone: 'Asia/Shanghai' });
    }
  }
  return null;
}

// Helper: check if market matches (skip filter when data has no market field)
function marketMatches(data: any, targetMarket: string): boolean {
  if (!data.market) return true; // no market tag → include (legacy data)
  return data.market.toLowerCase() === targetMarket.toLowerCase();
}

// Query market data by date: GET /api/history/market?date=2026-04-07&market=A-Share
router.get('/history/market', (req, res) => {
  const { date, market } = req.query;
  if (!date || typeof date !== 'string') {
    return res.status(400).json({ error: 'date parameter is required (YYYY-MM-DD)' });
  }
  const targetMarket = (market as string) || 'A-Share';

  try {
    const files = fs.readdirSync(HISTORY_DIR).sort().reverse();
    for (const f of files) {
      if (!f.startsWith('market_')) continue;
      try {
        const data = JSON.parse(fs.readFileSync(path.join(HISTORY_DIR, f), 'utf-8'));
        if (!marketMatches(data, targetMarket)) continue;
        const beijingDate = extractBeijingDate(data, f);
        if (beijingDate === date) {
          return res.json(data);
        }
      } catch {}
    }
    res.status(404).json({ error: `No market data found for ${targetMarket} on ${date}` });
  } catch (err) {
    console.error('Failed to query market history:', err);
    res.status(500).json({ error: 'Failed to query market history' });
  }
});

// List available dates: GET /api/history/dates?market=A-Share
router.get('/history/dates', (req, res) => {
  const targetMarket = ((req.query.market as string) || 'A-Share').toLowerCase();

  try {
    const files = fs.readdirSync(HISTORY_DIR).sort().reverse();
    const dates = new Set<string>();
    for (const f of files) {
      if (!f.startsWith('market_')) continue;
      try {
        const data = JSON.parse(fs.readFileSync(path.join(HISTORY_DIR, f), 'utf-8'));
        if (!marketMatches(data, targetMarket)) continue;
        const beijingDate = extractBeijingDate(data, f);
        if (beijingDate) dates.add(beijingDate);
      } catch {}
    }
    res.json([...dates].sort().reverse());
  } catch (err) {
    console.error('Failed to list history dates:', err);
    res.status(500).json({ error: 'Failed to list history dates' });
  }
});

router.get('/logs/optimization', (req, res) => {
  console.log('GET /api/logs/optimization called');
  try {
    const logs = JSON.parse(fs.readFileSync(LOG_FILE, 'utf-8'));
    res.json(logs);
  } catch (err) {
    console.error('Failed to read logs:', err);
    res.status(500).json({ error: 'Failed to read logs' });
  }
});

router.post('/history/save', (req, res) => {
  console.log('--- SAVE REQUEST START ---');
  const { type, data } = req.body;
  console.log(`Type: ${type}`);
  if (data) {
    console.log(`Data size: ${JSON.stringify(data).length} bytes`);
  } else {
    console.log('Data is missing');
  }
  
  if (!type || !data) {
    console.error('Missing type or data in save request');
    return res.status(400).json({ error: 'Type and data are required' });
  }
  try {
    saveAnalysis(type, data);
    console.log(`Successfully saved ${type} analysis to history`);
    res.json({ success: true });
  } catch (err) {
    console.error('Failed to save analysis to history:', err);
    res.status(500).json({ error: 'Failed to save analysis to history', details: err instanceof Error ? err.message : String(err) });
  }
  console.log('--- SAVE REQUEST END ---');
});

router.post('/logs/add', (req, res) => {
  const { field, oldValue, newValue, description } = req.body;
  if (!field || !description) {
    return res.status(400).json({ error: 'Field and description are required' });
  }
  addLogEntry(field, oldValue, newValue, description);
  res.json({ success: true });
});

export default router;
