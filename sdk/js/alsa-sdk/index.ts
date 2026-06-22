export interface AnalysisJob {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  symbol?: string;
  market?: string;
  progress?: { stage: string; percent: number };
  analysis_id?: string;
  result?: any;
  error_message?: string;
}

export interface MarketQuote {
  symbol: string;
  name?: string;
  price?: number;
  change?: number;
  changePercent?: number;
  volume?: number;
  market?: string;
}

export interface WatchlistItem {
  item_id?: string;
  symbol: string;
  name?: string;
  market: string;
  added_at?: string;
}

export interface Alert {
  alert_id?: string;
  symbol: string;
  market: string;
  entry_price?: number;
  target_price?: number;
  stop_loss?: number;
  status: string;
  created_at?: string;
}

export interface ApiKeyInfo {
  key_id: string;
  name: string;
  scopes: string[];
  rate_limit_override?: string;
  expires_at?: string;
  created_at?: string;
  last_used_at?: string;
  is_active: boolean;
}

export interface ALSAClientOptions {
  api_key?: string;
  token?: string;
  base_url?: string;
  timeout?: number;
  max_retries?: number;
}

interface ApiErrorResponse {
  success: false;
  error: { code: string; message: string };
}

interface ApiSuccessResponse<T> {
  success: true;
  data: T;
}

type ApiResponse<T> = ApiSuccessResponse<T> | ApiErrorResponse;

export class ALSAClientError extends Error {
  status_code: number;
  code: string;
  constructor(status_code: number, code: string, message: string) {
    super(`[${status_code}] ${code}: ${message}`);
    this.status_code = status_code;
    this.code = code;
  }
}

export class ALSAClient {
  private api_key?: string;
  private token?: string;
  private base_url: string;
  private timeout: number;
  private max_retries: number;

  constructor(options: ALSAClientOptions) {
    if (!options.api_key && !options.token) {
      throw new Error("Provide either api_key or token");
    }
    this.api_key = options.api_key;
    this.token = options.token;
    this.base_url = (options.base_url || "http://localhost:8001").replace(/\/+$/, "");
    this.timeout = options.timeout ?? 30000;
    this.max_retries = options.max_retries ?? 3;
  }

  private buildHeaders(): Record<string, string> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (this.api_key) {
      headers["X-API-Key"] = this.api_key;
    } else if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }
    return headers;
  }

  private async request<T>(method: string, path: string, body?: any): Promise<T> {
    const url = `${this.base_url}${path}`;
    const headers = this.buildHeaders();
    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= this.max_retries; attempt++) {
      try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), this.timeout);

        const resp = await fetch(url, {
          method,
          headers,
          body: body ? JSON.stringify(body) : undefined,
          signal: controller.signal,
        });
        clearTimeout(timer);

        if (resp.status === 429) {
          const retryAfter = parseInt(resp.headers.get("Retry-After") || "5", 10);
          console.warn(`Rate limited, retrying in ${retryAfter}s (attempt ${attempt + 1})`);
          await new Promise((r) => setTimeout(r, retryAfter * 1000));
          continue;
        }

        if (resp.status >= 500) {
          const wait = Math.min(2 ** attempt, 30) * 1000;
          console.warn(`Server error ${resp.status}, retrying in ${wait / 1000}s`);
          await new Promise((r) => setTimeout(r, wait));
          continue;
        }

        const json: ApiResponse<T> = await resp.json();

        if (!json.success) {
          const err = (json as ApiErrorResponse).error;
          throw new ALSAClientError(resp.status, err.code, err.message);
        }
        return (json as ApiSuccessResponse<T>).data;
      } catch (e: any) {
        if (e instanceof ALSAClientError) throw e;
        if (attempt < this.max_retries) {
          lastError = e;
          const wait = Math.min(2 ** attempt, 30) * 1000;
          await new Promise((r) => setTimeout(r, wait));
          continue;
        }
        throw new ALSAClientError(503, "CONNECTION_ERROR", e.message);
      }
    }
    throw new ALSAClientError(503, "MAX_RETRIES", "Exceeded maximum retries");
  }

  // ── Analysis ──

  async analyze(symbol: string, market: string, analysis_level = "standard", model?: string) {
    const payload: any = { symbol, market, analysis_level };
    if (model) payload.requested_model = model;
    return this.request<any>("POST", "/api/analysis/jobs", payload);
  }

  async getAnalysisJob(job_id: string) {
    return this.request<any>("GET", `/api/analysis/jobs/${job_id}`);
  }

  async getAnalysisRun(analysis_id: string) {
    return this.request<any>("GET", `/api/analysis/runs/${analysis_id}`);
  }

  async getAnalysisHistory(symbol: string) {
    return this.request<any[]>("GET", `/api/analysis/history/${symbol}`);
  }

  // ── Market ──

  async getMarketIndices(market = "A-Share") {
    return this.request<any>("GET", `/api/market/indices?market=${encodeURIComponent(market)}`);
  }

  async getQuote(symbol: string) {
    return this.request<any>("GET", `/api/market/quote/${encodeURIComponent(symbol)}`);
  }

  async getQuotes(symbols: string[]) {
    return this.request<any[]>("GET", `/api/market/quotes?symbols=${symbols.map(encodeURIComponent).join(",")}`);
  }

  async getHistory(symbol: string, period = "1mo", interval = "1d") {
    return this.request<any[]>("GET", `/api/market/history/${encodeURIComponent(symbol)}?period=${period}&interval=${interval}`);
  }

  async getMarketData(symbol: string, period = "1mo") {
    const [quote, history] = await Promise.all([
      this.getQuote(symbol),
      this.getHistory(symbol, period),
    ]);
    return { quote, history };
  }

  // ── Watchlist ──

  async getWatchlist() {
    const data = await this.request<any>("GET", "/api/watchlist/");
    return data?.items ?? data;
  }

  async addToWatchlist(symbol: string, name: string, market: string) {
    return this.request<any>("POST", "/api/watchlist/", { symbol, name, market });
  }

  async removeFromWatchlist(symbol: string, market: string) {
    await this.request<any>("DELETE", `/api/watchlist/${encodeURIComponent(symbol)}?market=${encodeURIComponent(market)}`);
    return true;
  }

  // ── Alerts ──

  async getAlerts() {
    const data = await this.request<any>("GET", "/api/alerts/");
    return data?.items ?? data;
  }

  async createAlert(symbol: string, market: string, entry_price: number, target_price: number, stop_loss: number) {
    return this.request<any>("POST", "/api/alerts/", { symbol, market, entry_price, target_price, stop_loss });
  }

  // ── API Keys ──

  async createApiKey(name: string, scopes?: string[], expires_in_days?: number) {
    const payload: any = { name };
    if (scopes) payload.scopes = scopes;
    if (expires_in_days) payload.expires_in_days = expires_in_days;
    return this.request<any>("POST", "/api/api-keys/", payload);
  }

  async listApiKeys() {
    return this.request<any[]>("GET", "/api/api-keys/");
  }

  async revokeApiKey(key_id: string) {
    await this.request<any>("DELETE", `/api/api-keys/${key_id}`);
    return true;
  }

  // ── Health ──

  async health() {
    return this.request<any>("GET", "/api/health");
  }
}
