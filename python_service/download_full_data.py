#!/usr/bin/env python3
import os
import sys
import time
import shutil
import logging
import argparse
import subprocess
import pandas as pd
import yfinance as yf
import akshare as ak

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def get_all_a_share_mainboard():
    logger.info("Fetching A-share mainboard stock symbols...")
    try:
        df = ak.stock_info_a_code_name()
        # Keep codes starting with 60 (Shanghai Mainboard) or 00 (Shenzhen Mainboard)
        mainboard_df = df[df["code"].str.startswith(("60", "00"))]
        codes = mainboard_df["code"].tolist()
        logger.info(f"Found {len(codes)} A-share mainboard stocks.")
        return codes
    except Exception as e:
        logger.warning(f"akshare stock_info_a_code_name failed: {e}. Trying fallback...")
    
    # Fallback: try to get from existing qlib instruments file
    try:
        instruments_file = os.path.expanduser("~/.qlib/qlib_data/cn_data/instruments/all.txt")
        if os.path.exists(instruments_file):
            with open(instruments_file) as f:
                lines = f.readlines()
            codes = []
            for line in lines:
                sym = line.split("\t")[0].strip()
                if sym.startswith("sh6") or sym.startswith("sz0") or sym.startswith("sz3"):
                    code = sym[2:]  # strip sh/sz prefix
                    codes.append(code)
            if codes:
                logger.info(f"Loaded {len(codes)} A-share codes from existing qlib instruments.")
                return codes
    except Exception as e2:
        logger.warning(f"Fallback from instruments file also failed: {e2}")
    
    logger.error("All methods failed. Using minimal fallback list.")
    return ["600519", "601398", "600036", "601318", "000858", "000333", "000001", "000002"]

def get_all_hk_share_mainboard():
    logger.info("Fetching HK-share mainboard stock symbols...")
    
    # Try SINA first (usually very stable for full lists)
    try:
        logger.info("Trying SINA HK spot API...")
        df = ak.stock_hk_spot()
        codes = df["代码"].tolist()
        mainboard_codes = [c for c in codes if not c.startswith("08")]
        if mainboard_codes:
            logger.info(f"SINA found {len(mainboard_codes)} HK mainboard stocks.")
            return mainboard_codes
    except Exception as e:
        logger.warning(f"SINA HK spot API failed: {e}")

    # Fallback 1: Eastmoney mainboard spot
    for retry in range(3):
        try:
            logger.info(f"Trying Eastmoney mainboard spot API (attempt {retry+1})...")
            df = ak.stock_hk_main_board_spot_em()
            codes = df["代码"].tolist()
            mainboard_codes = [c for c in codes if not c.startswith("08")]
            logger.info(f"Eastmoney mainboard found {len(mainboard_codes)} HK mainboard stocks.")
            return mainboard_codes
        except Exception as e:
            logger.warning(f"Eastmoney mainboard failed: {e}")
            time.sleep(1)

    # Fallback 2: Eastmoney all spot
    try:
        logger.info("Trying fallback Eastmoney HK spot API...")
        df = ak.stock_hk_spot_em()
        codes = df["代码"].tolist()
        mainboard_codes = [c for c in codes if not c.startswith("08")]
        logger.info(f"Eastmoney fallback found {len(mainboard_codes)} HK mainboard stocks.")
        return mainboard_codes
    except Exception as e:
        logger.error(f"Eastmoney fallback failed: {e}")
        # Return curated fallback list of top HK mainboard stocks
        return ["00700", "09988", "03690", "01810", "09618", "00001", "00005", "01299"]

def format_hk_code_for_yf(code: str) -> str:
    # Remove any non-digits
    clean_code = "".join(c for c in code if c.isdigit())
    val = int(clean_code)
    # yfinance expects 4 digits for codes < 10000, and 5 digits otherwise
    if val < 10000:
        return f"{str(val).zfill(4)}.HK"
    else:
        return f"{val}.HK"

def normalize_symbol_for_qlib(ticker: str) -> str:
    """Normalize yfinance ticker to Qlib symbol format.
    
    A-shares: 600519.SS -> sh600519, 000001.SZ -> sz000001
    HK-shares: 0700.HK -> 0700.hk (lowercase to match bridge's .lower())
    """
    if ticker.endswith(".SS"):
        code = ticker.replace(".SS", "")
        return f"sh{code}"
    elif ticker.endswith(".SZ"):
        code = ticker.replace(".SZ", "")
        return f"sz{code}"
    elif ticker.endswith(".HK"):
        # Store as lowercase .hk to match run_qlib_bridge.py which lowercases all symbols
        return ticker.lower()
    else:
        return ticker.lower()

def main():
    parser = argparse.ArgumentParser(description="Bulk download stock data and update Qlib.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of stocks to download (for dry-run/testing)")
    parser.add_argument("--start_date", type=str, default="2015-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end_date", type=str, default="2025-12-31", help="End date (YYYY-MM-DD)")
    parser.add_argument("--batch_size", type=int, default=100, help="Batch size for yfinance download")
    args = parser.parse_args()

    # 1. Fetch symbol list
    a_codes = get_all_a_share_mainboard()
    hk_codes = get_all_hk_share_mainboard()

    # Convert to yfinance tickers
    yf_tickers = []
    for code in a_codes:
        if code.startswith("6"):
            yf_tickers.append(f"{code}.SS")
        else:
            yf_tickers.append(f"{code}.SZ")

    for code in hk_codes:
        yf_tickers.append(format_hk_code_for_yf(code))

    # Apply limit if specified (dry-run)
    if args.limit is not None:
        logger.info(f"Limiting download to first {args.limit} symbols.")
        yf_tickers = yf_tickers[:args.limit]

    total_tickers = len(yf_tickers)
    logger.info(f"Starting download for {total_tickers} tickers from {args.start_date} to {args.end_date}...")

    # Create temporary folder for CSV files
    tmp_csv_dir = "/tmp/qlib_bulk_csv"
    shutil.rmtree(tmp_csv_dir, ignore_errors=True)
    os.makedirs(tmp_csv_dir, exist_ok=True)

    # 2. Download in batches
    success_count = 0
    start_time = time.time()

    for i in range(0, total_tickers, args.batch_size):
        batch = yf_tickers[i : i + args.batch_size]
        logger.info(f"Downloading batch {i // args.batch_size + 1} ({len(batch)} tickers)...")
        
        try:
            batch_df = yf.download(
                batch,
                start=args.start_date,
                end=args.end_date,
                group_by="ticker",
                threads=True,
                progress=False
            )
        except Exception as e:
            logger.error(f"Failed to download batch: {e}")
            continue

        if batch_df.empty:
            logger.warning("Empty batch dataframe returned.")
            continue

        # Extract levels and tickers
        if isinstance(batch_df.columns, pd.MultiIndex):
            downloaded_tickers = list(batch_df.columns.levels[0])
        else:
            downloaded_tickers = batch

        for ticker in batch:
            try:
                # Handle single vs multi-index columns
                if isinstance(batch_df.columns, pd.MultiIndex):
                    if ticker not in downloaded_tickers:
                        continue
                    df = batch_df[ticker].copy()
                else:
                    df = batch_df.copy()

                df = df.dropna(subset=["Close", "Open"])
                if df.empty:
                    continue

                df = df.reset_index()
                
                # Make columns case-insensitive
                df.columns = [str(c).lower().strip() for c in df.columns]
                
                # Find date column
                date_col = None
                for col in ["date", "index", "level_0"]:
                    if col in df.columns:
                        date_col = col
                        break
                if date_col is None:
                    continue

                df.rename(columns={date_col: "date"}, inplace=True)
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

                # Get adj close
                adj_close_col = None
                for col in ["adj close", "adjclose", "close"]:
                    if col in df.columns:
                        adj_close_col = col
                        break
                
                if adj_close_col and adj_close_col != "close":
                    df["factor"] = df[adj_close_col] / df["close"]
                    df["open"] = df["open"] * df["factor"]
                    df["high"] = df["high"] * df["factor"]
                    df["low"] = df["low"] * df["factor"]
                    df["close"] = df[adj_close_col]
                else:
                    df["factor"] = 1.0

                df["amount"] = df["volume"] * df["close"]
                df["symbol"] = normalize_symbol_for_qlib(ticker)

                # Select and save
                csv_df = df[["symbol", "date", "open", "close", "high", "low", "volume", "amount", "factor"]]
                csv_path = os.path.join(tmp_csv_dir, f"{df['symbol'].iloc[0]}.csv")
                csv_df.to_csv(csv_path, index=False)
                success_count += 1
            except Exception as ex:
                logger.debug(f"Failed to process ticker {ticker}: {ex}")

        # Sleep to avoid rate limiting
        time.sleep(1.5)

    duration = time.time() - start_time
    logger.info(f"Downloaded and formatted {success_count}/{total_tickers} symbols in {duration:.1f}s.")

    if success_count == 0:
        logger.error("No stock data downloaded successfully. Exiting.")
        sys.exit(1)

    # 3. Dump to Qlib binary format using venv_qlib
    logger.info("Converting CSVs to Qlib binary format...")
    qlib_dir = os.path.expanduser("~/.qlib/qlib_data/cn_data")
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    venv_python = os.path.join(project_root, ".venv_qlib", "bin", "python")
    dump_script = "/home/ubuntu/qlib/scripts/dump_bin.py"

    cmd = [
        venv_python, dump_script, "dump_all",
        "--data_path", tmp_csv_dir,
        "--qlib_dir", qlib_dir,
        "--symbol_field_name", "symbol",
        "--date_field_name", "date",
        "--include_fields", "open,close,high,low,volume,amount,factor"
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = "/home/ubuntu/qlib"
    
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        logger.error(f"Qlib dump failed: {result.stderr}")
        sys.exit(1)

    logger.info("Successfully converted to binary format.")

    # 4. Update calendars and instruments list
    logger.info("Updating Qlib calendar and instruments files...")
    
    # Ensure calendars directory exists and contains day.txt
    calendars_dir = os.path.join(qlib_dir, "calendars")
    os.makedirs(calendars_dir, exist_ok=True)
    day_txt = os.path.join(calendars_dir, "day.txt")
    
    # Generate business days from 2015 to 2030
    dates = pd.date_range("2015-01-01", "2030-12-31", freq="B")
    dates.strftime("%Y-%m-%d").to_series().to_csv(day_txt, index=False, header=False)
    logger.info(f"Rebuilt calendar in {day_txt}.")

    # Rebuild instruments list — merge new symbols with existing ones from features/
    instruments_dir = os.path.join(qlib_dir, "instruments")
    os.makedirs(instruments_dir, exist_ok=True)
    all_txt = os.path.join(instruments_dir, "all.txt")
    
    # Collect existing symbols from features directory
    features_dir = os.path.join(qlib_dir, "features")
    existing_symbols = set()
    if os.path.isdir(features_dir):
        for d in os.listdir(features_dir):
            if os.path.isdir(os.path.join(features_dir, d)):
                existing_symbols.add(d)
    
    # Add newly downloaded symbols
    for fn in os.listdir(tmp_csv_dir):
        if fn.endswith(".csv"):
            existing_symbols.add(fn.replace(".csv", ""))

    with open(all_txt, "w") as f:
        for sym in sorted(existing_symbols):
            f.write(f"{sym}\t2015-01-01\t2030-12-31\n")
            
    logger.info(f"Rebuilt instruments list in {all_txt} with {len(existing_symbols)} symbols (merged existing + new).")

    # Clean up temp folder
    shutil.rmtree(tmp_csv_dir, ignore_errors=True)
    logger.info("Done.")

if __name__ == "__main__":
    main()
