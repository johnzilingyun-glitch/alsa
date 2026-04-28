import sqlite3 from 'sqlite3';
import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DATA_DIR = path.join(process.cwd(), 'data');
const DB_PATH = path.join(DATA_DIR, 'alsa.db');

// Ensure data directory exists
if (!fs.existsSync(DATA_DIR)) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

export const db = new sqlite3.Database(DB_PATH, (err) => {
  if (err) {
    console.error('Error opening database', err.message);
  } else {
    console.log('Connected to the SQLite database at', DB_PATH);
    db.run('PRAGMA journal_mode = WAL;');
    initializeSchema();
  }
});

function initializeSchema() {
  db.serialize(() => {
    // Analysis Runs table
    db.run(`
      CREATE TABLE IF NOT EXISTS analysis_runs (
        analysis_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        symbol TEXT,
        market TEXT,
        status TEXT NOT NULL DEFAULT 'completed',
        prompt_version TEXT NOT NULL,
        model TEXT NOT NULL,
        input_snapshot_path TEXT,
        output_payload TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Watchlist table
    db.run(`
      CREATE TABLE IF NOT EXISTS watchlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        name TEXT,
        market TEXT NOT NULL,
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, market)
      )
    `);

    // Decision Journal table
    db.run(`
      CREATE TABLE IF NOT EXISTS decision_journal (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        analysis_id TEXT,
        symbol TEXT NOT NULL,
        market TEXT NOT NULL,
        action TEXT NOT NULL, -- 'buy', 'sell', 'hold'
        reasoning TEXT,
        price_at_decision REAL,
        confidence INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(analysis_id) REFERENCES analysis_runs(analysis_id)
      )
    `);

    console.log('Database schema initialized');
  });
}

export function query<T>(sql: string, params: any[] = []): Promise<T[]> {
  return new Promise((resolve, reject) => {
    db.all(sql, params, (err, rows) => {
      if (err) reject(err);
      else resolve(rows as T[]);
    });
  });
}

export function run(sql: string, params: any[] = []): Promise<{ lastID: number; changes: number }> {
  return new Promise((resolve, reject) => {
    db.serialize(() => {
      db.run(sql, params, function (err) {
        if (err) reject(err);
        else resolve({ lastID: this.lastID, changes: this.changes });
      });
    });
  });
}
