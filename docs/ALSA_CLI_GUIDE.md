# ALSA Institutional CLI User Guide

The ALSA CLI is a terminal-based tool for professional equity research. It runs the same
analysis pipeline as the web UI and generates standalone HTML research reports — for both
individual stocks and whole sectors/industries.

## 1. Installation & Setup

Run from the project root with the Python backend virtual environment active:

```bash
cd /home/ubuntu/work/alsa
source python_service/.venv/bin/activate   # or your venv of choice

# Verify the CLI is wired up
python python_service/cli.py --help
```

**API keys / credentials** are read from `.env` and `.env.runtime` via `load_dotenv`
(the CLI loads them automatically at startup). You do **not** store keys in the CLI config —
use the env files. The CLI config (`~/.alsa_config.json`) is only for non-secret preferences
such as the default model.

## 2. Configuration (`config`)

Settings are persisted in `~/.alsa_config.json`. Only non-secret values should go here.

| Command | Description |
| :--- | :--- |
| `python python_service/cli.py config show` | View current settings |
| `python python_service/cli.py config set model "deepseek-v4-pro"` | Set the default LLM used when `--model` is omitted |
| `python python_service/cli.py config set gemini_model "..."` | Alternative key name for the default model |
| `python python_service/cli.py config get model` | Read a single setting |
| `python python_service/cli.py config unset model` | Remove a setting (asks for confirmation) |

> Note: `analyze` / `sector` resolve the model in this order:
> CLI `--model` → config `model` → config `gemini_model` → `DEFAULT_LLM_MODEL` env var.
> Deprecated models (e.g. `gemini-1.5-pro`) are auto-downgraded to the default.

## 3. Stock Analysis (`analyze`)

The `analyze` command uses **Smart Recognition** — type a name or code, no need to remember
market prefixes. It resolves the symbol, runs the expert discussion pipeline, and writes an
HTML report.

### Basic usage
```bash
python python_service/cli.py analyze "贵州茅台"
python python_service/cli.py analyze "AAPL"
python python_service/cli.py analyze "00700"          # Tencent (HK)
```

### Interactive resolution
If a query matches multiple assets, the CLI prompts you to pick one:
```text
Multiple matches found. Please choose:
1. 腾讯控股 (00700 | HK-Share)
2. 腾讯音乐 (TME | US-Share)
Enter ID to select [1]: 1
```

### Options
| Option | Default | Values | Description |
| :--- | :--- | :--- | :--- |
| `--market` / `-m` | auto | `A-Share`, `HK-Share`, `US-Share` | Force a market instead of auto-detect |
| `--level` / `-l` | `standard` | `quick`, `standard`, `deep` | Analysis depth (drives discussion rounds & fields) |
| `--output` / `-o` | see §5 | any path | Custom HTML report path |
| `--model` | config/default | any model id | LLM model to use |
| `--guard` / `-g` | `high` | `none`, `low`, `medium`, `high` | Token spend guard level |
| `--verification-mode` / `-v` | `quick` | `quick`, `quality`, `extreme` | Verification strictness (matches web UI) |
| `--lang` | auto (by market) | `zh`, `en` | Report language |

Example:
```bash
python python_service/cli.py analyze "贵州茅台" -l deep -g medium -v quality
python python_service/cli.py analyze "AAPL" -m US-Share -o ./reports/apple.html
```

## 4. Sector Analysis (`sector`)

Analyzes an industry/sector with LLM-powered expert discussion and recommends stocks, then
writes a sector HTML report.

```bash
# Direct deep analysis of a named sector
python python_service/cli.py sector "半导体"
python python_service/cli.py sector "新能车" -o ./reports/ev.html

# No sector name → interactive A-share sector-rotation scan,
# then pick a sector from the results to analyze in depth
python python_service/cli.py sector
```

### Options
| Option | Default | Description |
| :--- | :--- | :--- |
| `--output` / `-o` | see §5 | Custom HTML report path |
| `--model` | config/default | LLM model to use |

## 5. Report Location

Reports are standalone HTML files.

- **Default directory**: `<project root>/reports/` (the CLI creates it automatically).
- **Default filename**:
  - Stock: `[SYMBOL]_report_[YYYYMMDD_HHMMSS].html` (e.g. `600519_report_20260712_153000.html`)
  - Sector: `sector_[NAME]_report_[YYYYMMDD_HHMMSS].html`
- **Custom path**: pass `-o /path/to/file.html` to override.

```bash
python python_service/cli.py analyze "贵州茅台" -o ./reports/maotai_june.html
```

## 6. Listing Past Jobs (`list`)

```bash
python python_service/cli.py list            # last 10 jobs
python python_service/cli.py list -n 20      # last 20 jobs
```

Shows Job ID, symbol, market, status, created-at, and level, read from the local SQLite DB.

## 7. Troubleshooting

- **`Could not find any assets matching ...`**: the symbol/name wasn't recognized. Try a fuller
  name, or pass `--market` explicitly.
- **`API_KEY_INVALID` / empty LLM output**: ensure the relevant key is set in `.env` /
  `.env.runtime` (not in CLI config).
- **`Database not found ... No jobs to list`**: the SQLite DB hasn't been initialized yet — run
  an analysis first, or check `DATABASE_URL`.
- **Garbled Chinese/emoji in terminal**: the CLI targets UTF-8. On a misconfigured locale,
  `export LANG=C.UTF-8` (or `zh_CN.UTF-8`).
- **Network errors during data fetch**: the pipeline retries automatically; ensure a stable
  connection and that the Python service's data providers are reachable.
