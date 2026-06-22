# ALSA JavaScript/TypeScript SDK

Client library for the [ALSA Institutional Stock Analysis API](https://alsa.example.com).

## Installation

```bash
npm install @alsa/sdk
```

## Quick Start

```typescript
import { ALSAClient } from "@alsa/sdk";

const client = new ALSAClient({ api_key: "alsa_your_key_here" });

// Get market data
const quote = await client.getQuote("AAPL");
console.log(quote);

// Run analysis
const job = await client.analyze("600519", "A-Share", "deep");
console.log(job.job_id);

// Poll for results
const result = await client.getAnalysisJob(job.job_id);
console.log(result.status);

// Watchlist
await client.addToWatchlist("600519", "贵州茅台", "A-Share");
const items = await client.getWatchlist();

// Alerts
await client.createAlert("600519", "A-Share", 1800, 2000, 1700);
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `api_key` | — | API key prefixed with `alsa_` |
| `token` | — | JWT access token |
| `base_url` | `http://localhost:8001` | API base URL |
| `timeout` | `30000` | HTTP timeout (ms) |
| `max_retries` | `3` | Retry attempts for 429/5xx |

## Error Handling

```typescript
import { ALSAClient, ALSAClientError } from "@alsa/sdk";

const client = new ALSAClient({ api_key: "alsa_..." });
try {
  await client.getQuote("INVALID");
} catch (e) {
  if (e instanceof ALSAClientError) {
    console.error(`Error ${e.status_code}: ${e.code} — ${e.message}`);
  }
}
```

## License

MIT
