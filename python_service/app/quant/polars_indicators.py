import polars as pl
from typing import List, Dict, Any

def compute_indicator_frame(rows: List[Dict[str, Any]]) -> pl.DataFrame:
    """
    Computes technical indicators (MA, MACD, RSI, Bollinger Bands, ATR, OBV, KDJ) using Polars expressions.
    """
    if not rows:
        return pl.DataFrame()

    df = pl.DataFrame(rows).sort("trade_date")
    
    # Pre-calculate shifted columns for True Range and OBV
    df = df.with_columns([
        pl.col("close").shift(1).alias("prev_close"),
    ])
    
    # 1. Moving Averages & Volume MAs
    df = df.with_columns([
        pl.col("close").rolling_mean(5).alias("ma_5"),
        pl.col("close").rolling_mean(20).alias("ma_20"),
        pl.col("close").rolling_mean(60).alias("ma_60"),
        pl.col("volume").rolling_mean(5).alias("avg_volume_5"),
        pl.col("volume").rolling_mean(20).alias("avg_volume_20"),
        pl.col("close").rolling_std(20).alias("std_20"),
    ])

    # Bollinger Bands (20, 2)
    df = df.with_columns([
        (pl.col("ma_20") + 2 * pl.col("std_20")).alias("bollinger_upper"),
        (pl.col("ma_20") - 2 * pl.col("std_20")).alias("bollinger_lower"),
    ])

    # Resistance/Support (Rolling Max/Min)
    df = df.with_columns([
        pl.col("high").rolling_max(20).alias("resistance_short"),
        pl.col("low").rolling_min(20).alias("support_short"),
        pl.col("high").rolling_max(60).alias("resistance_long"),
        pl.col("low").rolling_min(60).alias("support_long"),
    ])

    # 2. MACD (12, 26, 9)
    # Using simple EWM mean approximations for EMA
    df = df.with_columns([
        (pl.col("close").ewm_mean(span=12, adjust=False) - pl.col("close").ewm_mean(span=26, adjust=False)).alias("macd_line")
    ])
    df = df.with_columns([
        pl.col("macd_line").alias("macd")
    ])
    df = df.with_columns([
        pl.col("macd_line").ewm_mean(span=9, adjust=False).alias("macd_signal")
    ])
    df = df.with_columns([
        (pl.col("macd_line") - pl.col("macd_signal")).alias("macd_hist")
    ])

    # 3. RSI (14)
    diff = pl.col("close").diff()
    gain = pl.when(diff > 0).then(diff).otherwise(0)
    loss = pl.when(diff < 0).then(-diff).otherwise(0)
    
    alpha = 1.0 / 14
    avg_gain = gain.ewm_mean(alpha=alpha, adjust=False)
    avg_loss = loss.ewm_mean(alpha=alpha, adjust=False)
    
    rs = avg_gain / avg_loss
    df = df.with_columns([
        (100 - (100 / (1 + rs))).alias("rsi_14")
    ])
    
    # 4. ATR (Average True Range, 14)
    tr1 = pl.col("high") - pl.col("low")
    tr2 = (pl.col("high") - pl.col("prev_close")).abs()
    tr3 = (pl.col("low") - pl.col("prev_close")).abs()
    
    # Use pl.max_horizontal for row-wise max
    try:
        tr = pl.max_horizontal([tr1, tr2, tr3])
    except AttributeError:
        # Fallback for older polars versions
        tr = pl.fold(tr1, lambda acc, s: pl.when(acc > s).then(acc).otherwise(s), [tr2, tr3])
        
    df = df.with_columns([
        tr.ewm_mean(alpha=1.0/14, adjust=False).alias("atr_14")
    ])
    
    # 5. OBV (On-Balance Volume)
    obv_direction = pl.when(pl.col("close") > pl.col("prev_close")).then(pl.col("volume"))\
                      .when(pl.col("close") < pl.col("prev_close")).then(-pl.col("volume"))\
                      .otherwise(0)
    df = df.with_columns([
        obv_direction.cum_sum().alias("obv")
    ])
    
    # 6. KDJ (Stochastic Oscillator, 9, 3, 3)
    # RSV = (Close - Min(Low, 9)) / (Max(High, 9) - Min(Low, 9)) * 100
    low_9 = pl.col("low").rolling_min(9)
    high_9 = pl.col("high").rolling_max(9)
    rsv = ((pl.col("close") - low_9) / (high_9 - low_9 + 1e-10)) * 100
    
    # Using EWM with alpha=1/3 roughly approximates SMA(3) for K and D
    df = df.with_columns([
        rsv.ewm_mean(alpha=1/3, adjust=False).alias("kdj_k")
    ])
    df = df.with_columns([
        pl.col("kdj_k").ewm_mean(alpha=1/3, adjust=False).alias("kdj_d")
    ])
    df = df.with_columns([
        (3 * pl.col("kdj_k") - 2 * pl.col("kdj_d")).alias("kdj_j")
    ])
    
    # VWAP (Cumulative)
    # Cumulative Price * Volume / Cumulative Volume
    cum_pv = (pl.col("close") * pl.col("volume")).cum_sum()
    cum_v = pl.col("volume").cum_sum()
    df = df.with_columns([
        (cum_pv / (cum_v + 1e-10)).alias("vwap")
    ])

    return df
