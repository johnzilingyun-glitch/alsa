#!/usr/bin/env python3
"""Download A-share data via yfinance and write to Qlib bin format."""
import os
import sys
import time
import shutil
import logging
import subprocess
import pandas as pd
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TMP_CSV_DIR = "/tmp/qlib_a_share_csv"
QLIB_DIR = os.path.expanduser("~/.qlib/qlib_data/cn_data")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_PYTHON = os.path.join(PROJECT_ROOT, ".venv_qlib", "bin", "python")
DUMP_SCRIPT = "/home/ubuntu/qlib/scripts/dump_bin.py"


def get_a_share_codes_from_instruments():
    """Get A-share codes from existing qlib instruments file."""
    instruments_file = os.path.join(QLIB_DIR, "instruments", "all.txt")
    codes = []
    if os.path.exists(instruments_file):
        with open(instruments_file) as f:
            for line in f:
                sym = line.split("\t")[0].strip()
                if sym.startswith("sh6") or sym.startswith("sz0") or sym.startswith("sz3"):
                    code = sym[2:]
                    codes.append(code)
    return sorted(set(codes))


def download_batch(tickers, start_date, end_date):
    """Download a batch of tickers via yfinance."""
    try:
        batch_df = yf.download(
            tickers, start=start_date, end=end_date,
            group_by="ticker", threads=True, progress=False
        )
    except Exception as e:
        logger.error(f"yfinance download failed: {e}")
        return {}

    results = {}
    if batch_df.empty:
        return results

    for ticker in tickers:
        try:
            if isinstance(batch_df.columns, pd.MultiIndex):
                if ticker not in batch_df.columns.levels[0]:
                    continue
                df = batch_df[ticker].copy()
            else:
                df = batch_df.copy()

            df = df.dropna(subset=["Close", "Open"])
            if df.empty:
                continue

            df = df.reset_index()
            df.columns = [str(c).lower().strip() for c in df.columns]

            date_col = next((c for c in ["date", "index"] if c in df.columns), None)
            if not date_col:
                continue

            df["date"] = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d")

            adj_close_col = next((c for c in ["adj close", "adjclose"] if c in df.columns), None)
            if adj_close_col:
                df["factor"] = df[adj_close_col] / df["close"]
                df["open"] *= df["factor"]
                df["high"] *= df["factor"]
                df["low"] *= df["factor"]
                df["close"] = df[adj_close_col]
            else:
                df["factor"] = 1.0

            df["amount"] = df["volume"] * df["close"]

            if ticker.endswith(".SS"):
                symbol = f"sh{ticker.replace('.SS', '')}"
            elif ticker.endswith(".SZ"):
                symbol = f"sz{ticker.replace('.SZ', '')}"
            else:
                continue

            df["symbol"] = symbol
            results[symbol] = df[["symbol", "date", "open", "close", "high", "low", "volume", "amount", "factor"]]
        except Exception:
            pass

    return results


def main():
    parser = __import__("argparse").ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Limit number of stocks")
    parser.add_argument("--start_date", type=str, default="2015-01-01")
    parser.add_argument("--end_date", type=str, default="2025-12-31")
    parser.add_argument("--batch_size", type=int, default=100)
    args = parser.parse_args()

    codes = get_a_share_codes_from_instruments()
    if not codes:
        logger.error("No A-share codes found in instruments file.")
        sys.exit(1)

    if args.limit:
        codes = codes[:args.limit]

    tickers = []
    for code in codes:
        if code.startswith("6"):
            tickers.append(f"{code}.SS")
        else:
            tickers.append(f"{code}.SZ")

    logger.info(f"Downloading {len(tickers)} A-share stocks from {args.start_date} to {args.end_date}")

    os.makedirs(TMP_CSV_DIR, exist_ok=True)
    # Skip already downloaded stocks
    existing_csvs = set(f.replace(".csv", "") for f in os.listdir(TMP_CSV_DIR) if f.endswith(".csv"))
    original_count = len(tickers)
    tickers = [t for t in tickers if ("sh" if t.endswith(".SS") else "sz") + t[:6] not in existing_csvs]
    if existing_csvs:
        logger.info(f"Skipping {len(existing_csvs)} already downloaded stocks.")

    success = 0
    for i in range(0, len(tickers), args.batch_size):
        batch = tickers[i:i + args.batch_size]
        batch_num = i // args.batch_size + 1
        total_batches = (len(tickers) + args.batch_size - 1) // args.batch_size
        logger.info(f"Batch {batch_num}/{total_batches} ({len(batch)} tickers)...")

        results = download_batch(batch, args.start_date, args.end_date)
        for symbol, df in results.items():
            csv_path = os.path.join(TMP_CSV_DIR, f"{symbol}.csv")
            df.to_csv(csv_path, index=False)
            success += 1

        logger.info(f"  Got {len(results)}/{len(batch)} (total: {success})")
        time.sleep(1.5)

    logger.info(f"Downloaded {success}/{len(tickers)} stocks.")

    if success == 0:
        logger.error("No data downloaded.")
        sys.exit(1)

    # Convert to qlib bin
    logger.info("Converting to Qlib bin format...")
    cmd = [
        VENV_PYTHON, DUMP_SCRIPT, "dump_all",
        "--data_path", TMP_CSV_DIR,
        "--qlib_dir", QLIB_DIR,
        "--symbol_field_name", "symbol",
        "--date_field_name", "date",
        "--include_fields", "open,close,high,low,volume,amount,factor"
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = "/home/ubuntu/qlib"
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        logger.error(f"dump_bin failed: {result.stderr[-500:]}")
        sys.exit(1)
    logger.info("Bin conversion done.")

    # Rebuild instruments from ALL features (existing + new)
    logger.info("Rebuilding instruments list...")
    features_dir = os.path.join(QLIB_DIR, "features")
    all_symbols = set()
    if os.path.isdir(features_dir):
        for d in os.listdir(features_dir):
            if os.path.isdir(os.path.join(features_dir, d)):
                all_symbols.add(d.lower())

    instruments_dir = os.path.join(QLIB_DIR, "instruments")
    os.makedirs(instruments_dir, exist_ok=True)
    all_txt = os.path.join(instruments_dir, "all.txt")
    with open(all_txt, "w") as f:
        for sym in sorted(all_symbols):
            f.write(f"{sym}\t2015-01-01\t2030-12-31\n")
    logger.info(f"Instruments: {len(all_symbols)} symbols.")

    # Rebuild calendar
    calendars_dir = os.path.join(QLIB_DIR, "calendars")
    os.makedirs(calendars_dir, exist_ok=True)
    day_txt = os.path.join(calendars_dir, "day.txt")
    dates = pd.date_range("2015-01-01", "2030-12-31", freq="B")
    dates.strftime("%Y-%m-%d").to_series().to_csv(day_txt, index=False, header=False)
    logger.info("Calendar updated.")

    logger.info("Done.")


if __name__ == "__main__":
    main()
