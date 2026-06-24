import os
import shutil
import yfinance as yf
import pandas as pd
import logging

logger = logging.getLogger(__name__)

def normalize_symbol_for_qlib(symbol: str, market: str = "CN") -> str:
    """Normalize yfinance/native symbol to Qlib format (e.g. sh600519)."""
    if market == "CN":
        if symbol.startswith("6"):
            return f"sh{symbol}"
        elif symbol.startswith("0") or symbol.startswith("3"):
            return f"sz{symbol}"
        else:
            return f"sh{symbol}"
    return symbol

def download_and_update_qlib_data(
    symbol: str, 
    start_date: str, 
    end_date: str, 
    qlib_dir: str = os.path.expanduser("~/.qlib/qlib_data/cn_data"),
    market: str = "CN"
):
    """
    Downloads missing data from yfinance and dynamically converts it to Qlib bin format.
    """
    # 1. Download data via yfinance
    if market == "CN":
        clean_symbol = symbol.replace("SH", "").replace("SZ", "").replace("sh", "").replace("sz", "")
        if clean_symbol.startswith("6"):
            yf_symbol = f"{clean_symbol}.SS"
        else:
            yf_symbol = f"{clean_symbol}.SZ"
    else:
        yf_symbol = symbol

    logger.info(f"Downloading {yf_symbol} from yfinance for {start_date} to {end_date}...")
    try:
        import signal
        def _timeout_handler(signum, frame):
            raise TimeoutError("yfinance download timed out")
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(30)  # 30s hard timeout
        try:
            df = yf.download(yf_symbol, start=start_date, end=end_date, progress=False)
        finally:
            signal.alarm(0)
    except TimeoutError:
        logger.warning(f"yfinance download timed out for {yf_symbol}, skipping.")
        return False
    except Exception as e:
        logger.warning(f"yfinance download failed for {yf_symbol}: {e}")
        return False
    
    if df.empty:
        logger.warning(f"No data found for {yf_symbol} in the requested range.")
        return False

    # Flatten MultiIndex columns if present (yfinance >= 0.2.x)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]

    df = df.reset_index()
    
    # Rename columns to lowercase aggressively
    df.columns = [str(c).lower().strip() for c in df.columns]
    
    if "date" not in df.columns:
        if "index" in df.columns:
            df.rename(columns={"index": "date"}, inplace=True)
        elif "level_0" in df.columns:
            df.rename(columns={"level_0": "date"}, inplace=True)
    
    # Calculate factor (Adjusted Close / Close)
    if "adj close" in df.columns:
        df["factor"] = df["adj close"] / df["close"]
        # Apply factor to OHL
        df["open"] = df["open"] * df["factor"]
        df["high"] = df["high"] * df["factor"]
        df["low"] = df["low"] * df["factor"]
        df["close"] = df["adj close"]
    else:
        df["factor"] = 1.0

    # Calculate amount (approximation if not provided by yf)
    df["amount"] = df["volume"] * df["close"]
    
    df["symbol"] = normalize_symbol_for_qlib(symbol, market)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    
    # Select specific columns
    csv_df = df[["symbol", "date", "open", "close", "high", "low", "volume", "amount", "factor"]]
    
    # Save to temporary CSV
    tmp_csv_dir = "/tmp/qlib_update_csv"
    os.makedirs(tmp_csv_dir, exist_ok=True)
    csv_path = os.path.join(tmp_csv_dir, f"{df['symbol'].iloc[0]}.csv")
    csv_df.to_csv(csv_path, index=False)
    
    logger.info(f"Saved yfinance data to {csv_path}. Converting to Qlib bin format...")

    # 3. Use Qlib DumpDataUpdate to update the binary data
    # We will invoke the dump_bin.py script from the cloned repo.
    import subprocess
    dump_script = "/home/ubuntu/qlib/scripts/dump_bin.py"
    
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    venv_python = os.path.join(project_root, ".venv_qlib", "bin", "python")
    
    # Ensure calendars directory exists and has day.txt
    calendars_dir = os.path.join(qlib_dir, "calendars")
    os.makedirs(calendars_dir, exist_ok=True)
    day_txt = os.path.join(calendars_dir, "day.txt")
    if not os.path.exists(day_txt):
        dates = pd.date_range("2010-01-01", "2030-12-31", freq="B")
        dates.strftime("%Y-%m-%d").to_series().to_csv(day_txt, index=False, header=False)
        
    # Ensure instruments directory exists and has all.txt
    instruments_dir = os.path.join(qlib_dir, "instruments")
    os.makedirs(instruments_dir, exist_ok=True)
    all_txt = os.path.join(instruments_dir, "all.txt")
    with open(all_txt, "a") as f:
        f.write(f"{csv_df['symbol'].iloc[0]}\t2010-01-01\t2030-12-31\n")
        
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
        logger.error(f"Qlib data dump failed: {result.stderr}")
        return False
        
    # Pad calendar to avoid IndexError in Qlib backtest utils get_step_time
    calendar_path = os.path.join(qlib_dir, "calendars", "day.txt")
    if os.path.exists(calendar_path):
        try:
            with open(calendar_path, "r") as f:
                lines = f.readlines()
            if lines:
                last_date = pd.to_datetime(lines[-1].strip())
                next_date = last_date
                for _ in range(5):
                    next_date += pd.Timedelta(days=1)
                    while next_date.weekday() >= 5:
                        next_date += pd.Timedelta(days=1)
                    if next_date.strftime("%Y-%m-%d") not in [l.strip() for l in lines[-10:]]:
                        lines.append(next_date.strftime("%Y-%m-%d") + "\n")
                with open(calendar_path, "w") as f:
                    f.writelines(lines)
        except Exception as e:
            logger.warning(f"Failed to pad calendar: {e}")
            
    logger.info("Successfully updated global Qlib data with missing yfinance records.")
    
    # Cleanup
    shutil.rmtree(tmp_csv_dir, ignore_errors=True)
    return True
