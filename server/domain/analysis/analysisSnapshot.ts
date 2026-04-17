export interface AnalysisRunRecord {
  analysisId: string;
  kind: 'stock' | 'market';
  symbol?: string;
  market?: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  promptVersion: string;
  model: string;
  inputSnapshotPath?: string;
  outputPayload: Record<string, unknown>;
  createdAt?: string;
}

export interface AnalysisRepository {
  save(record: AnalysisRunRecord): Promise<void>;
  getById(analysisId: string): Promise<AnalysisRunRecord | null>;
  getLatestStockAnalysis(symbol: string, market: string): Promise<AnalysisRunRecord | null>;
  listRecent(options: { limit?: number; kind?: 'stock' | 'market' }): Promise<AnalysisRunRecord[]>;
}
