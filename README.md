<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# AI Quantitative Trading & Research Platform (ALSA)

A comprehensive cross-market quantitative trading system that integrates LLM-based intelligent signal generation, multi-market simulated execution (Paper Trading), and real-time dashboard analytics.

## System Architecture

The project consists of three core components:

### 1. Frontend Dashboard (React + Vite)
- Real-time portfolio monitoring, account analytics, and AI signal tracking.
- **Run Command:** `npm install && npm run dev`
- **Configuration:** Settings in `.env.local`.

### 2. Backend Service (FastAPI - Python 3.12)
- Handles core CRUD operations for accounts, trades, and anomalies via SQLite.
- Exposes API endpoints (`/api/v1/mock-trading/*`) for the frontend.
- Integrates the event-driven intelligent signal center for real-time order execution.
- **Path:** `python_service/`
- **Environment:** Managed by `uv` (`.venv`).
- **Run Command:** `cd python_service && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`

### 3. High-Fidelity Simulation Engine (Qlib - Python 3.9)
- A standalone execution engine (`SimulatorExecutor`) used to align mathematical rigor with Qlib rules (e.g., A-share 100-lot downward rounding, high-precision commission, and slippage deduction).
- Real-time trading triggers from FastAPI use the `market_configs.py` module from this layer for exact alignment, operating as a transparent Facade.
- **Path:** `python_service/paper_trading_system/`
- **Environment:** Requires a dedicated Python 3.9 environment to avoid Cython build errors with Qlib.
- **Setup Command:** 
  ```bash
  cd python_service/paper_trading_system
  uv venv -p 3.9 .venv_qlib
  source .venv_qlib/bin/activate
  uv pip install -r requirements.txt
  ```

## Paper Trading (V1.0) Key Features
- **Strict Lot Sizing:** Automatically truncates A-Share target allocations to multiples of 100 shares.
- **High-Fidelity Cost Emulation:** Integrates actual market stamp duties and minimum execution costs into the real-time SQLite database engine.
- **Anomaly Detection:** Scans for abnormal spikes and drops across portfolios and individual stock holdings, pushing them to the UI's Anomaly Log.
