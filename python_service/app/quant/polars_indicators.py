import polars as pl
from typing import List, Dict, Any

def compute_indicator_frame(rows: List[Dict[str, Any]]) -> pl.DataFrame:
    """
    Computes technical indicators (MA, MACD, RSI) using Polars expressions.
    """
    if not rows:
        return pl.DataFrame()

    df = pl.DataFrame(rows).sort("trade_date")
    
    # 1. Moving Averages
    df = df.with_columns([
        pl.col("close").rolling_mean(5).alias("ma_5"),
        pl.col("close").rolling_mean(20).alias("ma_20"),
        pl.col("close").rolling_mean(60).alias("ma_60"),
        pl.col("volume").rolling_mean(5).alias("avg_volume_5"),
        pl.col("volume").rolling_mean(20).alias("avg_volume_20"),
    ])

    # Resistance/Support (Rolling Max/Min)
    df = df.with_columns([
        pl.col("high").rolling_max(20).alias("resistance_short"),
        pl.col("low").rolling_min(20).alias("support_short"),
        pl.col("high").rolling_max(60).alias("resistance_long"),
        pl.col("low").rolling_min(60).alias("support_long"),
    ])

    # 2. MACD (12, 26, 9)
    # Note: Using exponential moving averages
    ema_12 = df.select(pl.col("close").ewm_mean(span=12))
    ema_26 = df.select(pl.col("close").ewm_mean(span=26))
    
    df = df.with_columns([
        (pl.col("close").ewm_mean(span=12) - pl.col("close").ewm_mean(span=26)).alias("macd")
    ])

    # 3. RSI (14)
    # rsi = 100 - (100 / (1 + RS))
    diff = pl.col("close").diff()
    gain = pl.when(diff > 0).then(diff).otherwise(0)
    loss = pl.when(diff < 0).then(-diff).otherwise(0)
    
    avg_gain = gain.rolling_mean(14)
    avg_loss = loss.rolling_mean(14)
    
    rs = avg_gain / avg_loss
    df = df.with_columns([
        (100 - (100 / (1 + rs))).alias("rsi_14")
    ])

    return df
