#!/usr/bin/env python3
"""Download A-share data via AkShare and write to Qlib bin format."""
import os
import sys
import time
import shutil
import logging
import argparse
import subprocess
import pandas as pd
import akshare as ak
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TMP_CSV_DIR = "/tmp/qlib_akshare_csv"
QLIB_DIR = os.path.expanduser("~/.qlib/qlib_data/cn_data")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_PYTHON = os.path.join(PROJECT_ROOT, ".venv_qlib", "bin", "python")
DUMP_SCRIPT = "/home/ubuntu/qlib/scripts/dump_bin.py"


def get_a_share_codes():
    logger.info("Fetching A-share stock codes...")
    try:
        df = ak.stock_info_a_code_name()
        codes = df["code"].tolist()
        logger.info(f"Found {len(codes)} A-share stocks.")
        return codes
    except Exception as e:
        logger.error(f"Failed to fetch codes: {e}")
        return ["600519", "601398", "600036", "601318", "000858", "000333", "000001"]


def download_stock(code, start_date, end_date):
    try:
        df = ak.stock_zh_a_hist(
            symbol=code, period="daily",
            start_date=start_date, end_date=end_date,
            adjust="qfq"
        )
        if df is None or df.empty:
            return None

        df = df.rename(columns={
            "日期": "date", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume",
            "成交额": "amount", "换手率": "turnover",
        })

        if code.startswith("6"):
            symbol = f"sh{code}"
        else:
            symbol = f"sz{code}"

        df["symbol"] = symbol
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df["factor"] = 1.0

        cols = ["symbol", "date", "open", "close", "high", "low", "volume", "amount", "factor"]
        return df[[c for c in cols if c in df.columns]]
    except Exception as e:
        logger.debug(f"Failed for {code}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Limit number of stocks (for testing)")
    parser.add_argument("--start_date", type=str, default="20200101", help="Start date YYYYMMDD")
    parser.add_argument("--end_date", type=str, default=datetime.now().strftime("%Y%m%d"), help="End date YYYYMMDD")
    parser.add_argument("--skip_download", action="store_true", help="Skip download, use existing CSVs")
    args = parser.parse_args()

    codes = get_a_share_codes()
    if args.limit:
        codes = codes[:args.limit]
    logger.info(f"Will download {len(codes)} stocks from {args.start_date} to {args.end_date}")

    if not args.skip_download:
        shutil.rmtree(TMP_CSV_DIR, ignore_errors=True)
        os.makedirs(TMP_CSV_DIR, exist_ok=True)

        success = 0
        for i, code in enumerate(codes):
            if i > 0 and i % 50 == 0:
                logger.info(f"Progress: {i}/{len(codes)} ({success} ok)")
                time.sleep(2)
            df = download_stock(code, args.start_date, args.end_date)
            if df is not None and not df.empty:
                csv_path = os.path.join(TMP_CSV_DIR, f"{'sh' if code.startswith('6') else 'sz'}{code}.csv")
                df.to_csv(csv_path, index=False)
                success += 1
            time.sleep(0.3)

        logger.info(f"Downloaded {success}/{len(codes)} stocks to CSV.")

    csv_count = len([f for f in os.listdir(TMP_CSV_DIR) if f.endswith(".csv")]) if os.path.exists(TMP_CSV_DIR) else 0
    if csv_count == 0:
        logger.error("No CSV files found. Exiting.")
        sys.exit(1)

    logger.info(f"Converting {csv_count} CSVs to Qlib bin format...")
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
        logger.error(f"dump_bin failed: {result.stderr}")
        sys.exit(1)
    logger.info("Bin conversion done.")

    logger.info("Updating calendar and instruments...")
    calendars_dir = os.path.join(QLIB_DIR, "calendars")
    os.makedirs(calendars_dir, exist_ok=True)
    day_txt = os.path.join(calendars_dir, "day.txt")
    dates = pd.date_range("2015-01-01", "2030-12-31", freq="B")
    dates.strftime("%Y-%m-%d").to_series().to_csv(day_txt, index=False, header=False)

    instruments_dir = os.path.join(QLIB_DIR, "instruments")
    os.makedirs(instruments_dir, exist_ok=True)
    all_txt = os.path.join(instruments_dir, "all.txt")
    symbols = sorted([f.replace(".csv", "") for f in os.listdir(TMP_CSV_DIR) if f.endswith(".csv")])
    with open(all_txt, "w") as f:
        for sym in symbols:
            f.write(f"{sym}\t2015-01-01\t2030-12-31\n")
    logger.info(f"Instruments: {len(symbols)} symbols written to {all_txt}")

    shutil.rmtree(TMP_CSV_DIR, ignore_errors=True)
    logger.info("Done.")


if __name__ == "__main__":
    main()
