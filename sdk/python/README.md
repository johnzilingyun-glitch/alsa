# ALSA Python SDK

Client library for the [ALSA Institutional Stock Analysis API](https://alsa.example.com).

## Installation

```bash
pip install alsa-sdk
```

## Quick Start

```python
from alsa_sdk import ALSAClient

# With API key (recommended)
client = ALSAClient(api_key="alsa_your_key_here")

# Or with JWT token
client = ALSAClient(token="eyJhbGciOi...")

# Get market data
quote = client.get_quote("AAPL")
print(quote)

# Run analysis
job = client.analyze(symbol="600519", market="A-Share", analysis_level="deep")
print(job["job_id"])

# Poll for results
result = client.get_analysis_job(job["job_id"])
print(result["status"])

# Watchlist
client.add_to_watchlist("600519", "贵州茅台", "A-Share")
items = client.get_watchlist()

# Alerts
alert = client.create_alert("600519", "A-Share", entry_price=1800, target_price=2000, stop_loss=1700)
```

## Error Handling

```python
from alsa_sdk import ALSAClient
from alsa_sdk.client import ALSAClientError

client = ALSAClient(api_key="alsa_...")
try:
    result = client.get_quote("INVALID")
except ALSAClientError as e:
    print(f"Error {e.status_code}: {e.code} — {e.message}")
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `api_key` | — | API key prefixed with `alsa_` |
| `token` | — | JWT access token |
| `base_url` | `http://localhost:8001` | API base URL |
| `timeout` | `30.0` | HTTP timeout (seconds) |
| `max_retries` | `3` | Retry attempts for 429/5xx |

## License

MIT
