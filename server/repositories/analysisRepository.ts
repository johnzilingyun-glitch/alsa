import { AnalysisRepository, AnalysisRunRecord } from '../domain/analysis/analysisSnapshot.js';
import { run, query } from '../db/client.js';

export function createAnalysisRepository(): AnalysisRepository {
  return {
    async save(record: AnalysisRunRecord) {
      const sql = `
        INSERT OR REPLACE INTO analysis_runs (
          analysis_id, kind, symbol, market, status, 
          prompt_version, model, input_snapshot_path, output_payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      `;
      await run(sql, [
        record.analysisId,
        record.kind,
        record.symbol || null,
        record.market || null,
        record.status,
        record.promptVersion,
        record.model,
        record.inputSnapshotPath || null,
        JSON.stringify(record.outputPayload)
      ]);
    },

    async getById(analysisId: string) {
      const rows = await query<any>(
        'SELECT * FROM analysis_runs WHERE analysis_id = ?',
        [analysisId]
      );
      if (rows.length === 0) return null;
      return mapRowToRecord(rows[0]);
    },

    async getLatestStockAnalysis(symbol: string, market: string) {
      const rows = await query<any>(
        'SELECT * FROM analysis_runs WHERE kind = "stock" AND symbol = ? AND market = ? ORDER BY created_at DESC LIMIT 1',
        [symbol, market]
      );
      if (rows.length === 0) return null;
      return mapRowToRecord(rows[0]);
    },

    async listRecent(options: { limit?: number; kind?: 'stock' | 'market' }) {
      let sql = 'SELECT * FROM analysis_runs';
      const params: any[] = [];
      
      if (options.kind) {
        sql += ' WHERE kind = ?';
        params.push(options.kind);
      }
      
      sql += ' ORDER BY created_at DESC';
      
      if (options.limit) {
        sql += ' LIMIT ?';
        params.push(options.limit);
      }

      const rows = await query<any>(sql, params);
      return rows.map(mapRowToRecord);
    }
  };
}

function mapRowToRecord(row: any): AnalysisRunRecord {
  return {
    analysisId: row.analysis_id,
    kind: row.kind,
    symbol: row.symbol,
    market: row.market,
    status: row.status,
    promptVersion: row.prompt_version,
    model: row.model,
    inputSnapshotPath: row.input_snapshot_path,
    outputPayload: JSON.parse(row.output_payload || '{}'),
    createdAt: row.created_at
  };
}
