"""
Quantitative Technical Analysis Engine
──────────────────────────────────────
Five-strategy weighted ensemble producing structured trading signals.
Inspired by virattt/ai-hedge-fund (technicals.py) but adapted for
A-Share / HK / US markets and our AkShare data pipeline.

Strategies:
  1. Trend Following     (EMA crossover + ADX strength)
  2. Mean Reversion      (Z-score + Bollinger Bands + RSI)
  3. Momentum            (1m/3m/6m price momentum + volume)
  4. Volatility Analysis (hist vol regime + ATR)
  5. Statistical Arb     (Hurst exponent + skewness/kurtosis)
"""

from __future__ import annotations
import math
import numpy as np
import pandas as pd
from typing import Any


# ── Helpers ──────────────────────────────────────────────────────────

def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert a value to float, handling NaN / None / Inf."""
    try:
        if value is None:
            return default
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError, OverflowError):
        return default


# ── Core Indicator Calculations ─────────────────────────────────────

def calculate_ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False).mean()


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).fillna(0.0)
    loss = (-delta.where(delta < 0, 0.0)).fillna(0.0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calculate_bollinger_bands(
    close: pd.Series, window: int = 20, num_std: float = 2.0
) -> tuple[pd.Series, pd.Series]:
    sma = close.rolling(window).mean()
    std = close.rolling(window).std()
    return sma + std * num_std, sma - std * num_std


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Average Directional Index — measures trend strength (0-100)."""
    high, low, close = df["high"], df["low"], df["close"]

    high_low = high - low
    high_close = (high - close.shift()).abs()
    low_close = (low - close.shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

    up_move = high - high.shift()
    down_move = low.shift() - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    plus_dm_s = pd.Series(plus_dm, index=df.index)
    minus_dm_s = pd.Series(minus_dm, index=df.index)

    tr_ema = tr.ewm(span=period).mean()
    plus_di = 100 * (plus_dm_s.ewm(span=period).mean() / tr_ema)
    minus_di = 100 * (minus_dm_s.ewm(span=period).mean() / tr_ema)

    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx = dx.ewm(span=period).mean()

    return pd.DataFrame({"adx": adx, "+di": plus_di, "-di": minus_di}, index=df.index)


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    return ranges.max(axis=1).rolling(period).mean()


def calculate_hurst_exponent(price_series: pd.Series, max_lag: int = 20) -> float:
    """
    Hurst exponent:
      H < 0.5 → mean-reverting
      H ≈ 0.5 → random walk
      H > 0.5 → trending
    """
    prices = price_series.dropna().values
    if len(prices) < max_lag + 2:
        return 0.5

    lags = range(2, min(max_lag, len(prices) // 2))
    tau = []
    for lag in lags:
        diffs = prices[lag:] - prices[:-lag]
        std = np.std(diffs)
        tau.append(max(1e-8, np.sqrt(std)))

    if len(tau) < 2:
        return 0.5

    try:
        reg = np.polyfit(np.log(list(lags)), np.log(tau), 1)
        return float(reg[0])
    except (ValueError, RuntimeWarning):
        return 0.5


# ── Strategy Calculators ────────────────────────────────────────────

def calculate_trend_signals(df: pd.DataFrame) -> dict:
    """EMA crossover + ADX trend strength."""
    close = df["close"]
    ema_8 = calculate_ema(close, 8)
    ema_21 = calculate_ema(close, 21)
    ema_55 = calculate_ema(close, 55)

    adx_df = calculate_adx(df, 14)
    adx_val = safe_float(adx_df["adx"].iloc[-1])
    trend_strength = adx_val / 100.0

    short_trend = bool(ema_8.iloc[-1] > ema_21.iloc[-1])
    medium_trend = bool(ema_21.iloc[-1] > ema_55.iloc[-1])

    if short_trend and medium_trend:
        signal, confidence = "bullish", trend_strength
    elif not short_trend and not medium_trend:
        signal, confidence = "bearish", trend_strength
    else:
        signal, confidence = "neutral", 0.5

    return {
        "signal": signal,
        "confidence": round(min(max(confidence, 0), 1), 3),
        "metrics": {
            "adx": round(adx_val, 2),
            "ema_8": round(safe_float(ema_8.iloc[-1]), 2),
            "ema_21": round(safe_float(ema_21.iloc[-1]), 2),
            "ema_55": round(safe_float(ema_55.iloc[-1]), 2),
            "trend_strength": round(trend_strength, 3),
        },
    }


def calculate_mean_reversion_signals(df: pd.DataFrame) -> dict:
    """Z-score vs 50-day MA + Bollinger Bands + RSI."""
    close = df["close"]
    ma_50 = close.rolling(window=50).mean()
    std_50 = close.rolling(window=50).std().replace(0, np.nan)
    z_score = (close - ma_50) / std_50

    bb_upper, bb_lower = calculate_bollinger_bands(close)
    bb_width = bb_upper - bb_lower
    price_vs_bb = (close.iloc[-1] - bb_lower.iloc[-1]) / max(bb_width.iloc[-1], 1e-8)

    rsi_14 = calculate_rsi(close, 14)
    rsi_28 = calculate_rsi(close, 28)

    z = safe_float(z_score.iloc[-1])
    pvb = safe_float(price_vs_bb)

    if z < -2 and pvb < 0.2:
        signal = "bullish"
        confidence = min(abs(z) / 4, 1.0)
    elif z > 2 and pvb > 0.8:
        signal = "bearish"
        confidence = min(abs(z) / 4, 1.0)
    else:
        signal = "neutral"
        confidence = 0.5

    return {
        "signal": signal,
        "confidence": round(confidence, 3),
        "metrics": {
            "z_score": round(z, 3),
            "price_vs_bb": round(pvb, 3),
            "rsi_14": round(safe_float(rsi_14.iloc[-1]), 2),
            "rsi_28": round(safe_float(rsi_28.iloc[-1]), 2),
        },
    }


def calculate_momentum_signals(df: pd.DataFrame) -> dict:
    """Multi-timeframe price + volume momentum."""
    returns = df["close"].pct_change()
    mom_1m = returns.rolling(21).sum()
    mom_3m = returns.rolling(63).sum()
    mom_6m = returns.rolling(126).sum()

    volume_ma = df["volume"].rolling(21).mean().replace(0, np.nan)
    volume_momentum = df["volume"] / volume_ma

    m1 = safe_float(mom_1m.iloc[-1])
    m3 = safe_float(mom_3m.iloc[-1])
    m6 = safe_float(mom_6m.iloc[-1])
    momentum_score = 0.4 * m1 + 0.3 * m3 + 0.3 * m6

    vol_conf = safe_float(volume_momentum.iloc[-1]) > 1.0

    if momentum_score > 0.05 and vol_conf:
        signal, confidence = "bullish", min(abs(momentum_score) * 5, 1.0)
    elif momentum_score < -0.05 and vol_conf:
        signal, confidence = "bearish", min(abs(momentum_score) * 5, 1.0)
    else:
        signal, confidence = "neutral", 0.5

    return {
        "signal": signal,
        "confidence": round(confidence, 3),
        "metrics": {
            "momentum_1m": round(m1, 4),
            "momentum_3m": round(m3, 4),
            "momentum_6m": round(m6, 4),
            "momentum_score": round(momentum_score, 4),
            "volume_momentum": round(safe_float(volume_momentum.iloc[-1]), 3),
        },
    }


def calculate_volatility_signals(df: pd.DataFrame) -> dict:
    """Volatility regime detection."""
    returns = df["close"].pct_change()
    hist_vol = returns.rolling(21).std() * math.sqrt(252)
    vol_ma = hist_vol.rolling(63).mean()
    vol_std = hist_vol.rolling(63).std().replace(0, np.nan)
    vol_regime = hist_vol / vol_ma.replace(0, np.nan)
    vol_z_score = (hist_vol - vol_ma) / vol_std

    atr = calculate_atr(df)
    atr_ratio = atr / df["close"].replace(0, np.nan)

    vr = safe_float(vol_regime.iloc[-1], 1.0)
    vz = safe_float(vol_z_score.iloc[-1], 0.0)

    if vr < 0.8 and vz < -1:
        signal, confidence = "bullish", min(abs(vz) / 3, 1.0)
    elif vr > 1.2 and vz > 1:
        signal, confidence = "bearish", min(abs(vz) / 3, 1.0)
    else:
        signal, confidence = "neutral", 0.5

    return {
        "signal": signal,
        "confidence": round(confidence, 3),
        "metrics": {
            "historical_volatility": round(safe_float(hist_vol.iloc[-1]), 4),
            "volatility_regime": round(vr, 3),
            "volatility_z_score": round(vz, 3),
            "atr_ratio": round(safe_float(atr_ratio.iloc[-1]), 4),
        },
    }


def calculate_stat_arb_signals(df: pd.DataFrame) -> dict:
    """Statistical arbitrage via Hurst + skew/kurtosis."""
    returns = df["close"].pct_change()
    skew = returns.rolling(63).skew()
    kurt = returns.rolling(63).kurt()

    hurst = calculate_hurst_exponent(df["close"])

    sk = safe_float(skew.iloc[-1])

    if hurst < 0.4 and sk > 1:
        signal, confidence = "bullish", (0.5 - hurst) * 2
    elif hurst < 0.4 and sk < -1:
        signal, confidence = "bearish", (0.5 - hurst) * 2
    else:
        signal, confidence = "neutral", 0.5

    return {
        "signal": signal,
        "confidence": round(min(max(confidence, 0), 1), 3),
        "metrics": {
            "hurst_exponent": round(hurst, 4),
            "skewness": round(sk, 4),
            "kurtosis": round(safe_float(kurt.iloc[-1]), 4),
        },
    }


# ── Weighted Signal Fusion ──────────────────────────────────────────

STRATEGY_WEIGHTS = {
    "trend": 0.25,
    "mean_reversion": 0.20,
    "momentum": 0.25,
    "volatility": 0.15,
    "stat_arb": 0.15,
}

SIGNAL_MAP = {"bullish": 1, "neutral": 0, "bearish": -1}


def weighted_signal_combination(signals: dict[str, dict], weights: dict[str, float]) -> dict:
    """Weighted ensemble of all strategy signals."""
    weighted_sum = 0.0
    total_confidence = 0.0

    for strategy, sig_data in signals.items():
        numeric = SIGNAL_MAP.get(sig_data["signal"], 0)
        w = weights.get(strategy, 0)
        c = sig_data["confidence"]
        weighted_sum += numeric * w * c
        total_confidence += w * c

    if total_confidence > 0:
        final_score = weighted_sum / total_confidence
    else:
        final_score = 0.0

    if final_score > 0.2:
        signal = "bullish"
    elif final_score < -0.2:
        signal = "bearish"
    else:
        signal = "neutral"

    return {
        "signal": signal,
        "confidence": round(abs(final_score), 3),
        "weighted_score": round(final_score, 4),
    }


# ── Public API ──────────────────────────────────────────────────────

def analyze(df: pd.DataFrame) -> dict:
    """
    Run the full 5-strategy ensemble on an OHLCV DataFrame.
    
    Expects a DataFrame with columns: close, open, high, low, volume
    sorted chronologically (oldest → newest), minimum 60 rows.
    
    Returns a structured dict with combined signal + per-strategy breakdown.
    """
    if len(df) < 30:
        return {
            "signal": "neutral",
            "confidence": 0,
            "error": f"Insufficient data: {len(df)} rows (need ≥30)",
        }

    # Calculate MAs for the experts - ensure they return a value even if history is short
    ma5 = df["close"].rolling(window=5, min_periods=1).mean().iloc[-1]
    ma20 = df["close"].rolling(window=20, min_periods=1).mean().iloc[-1]
    ma60 = df["close"].rolling(window=min(60, len(df)), min_periods=1).mean().iloc[-1]

    # Calculate all 5 strategies
    trend = calculate_trend_signals(df)
    mean_rev = calculate_mean_reversion_signals(df)
    momentum = calculate_momentum_signals(df)
    volatility = calculate_volatility_signals(df)
    stat_arb = calculate_stat_arb_signals(df)

    # Combine
    all_signals = {
        "trend": trend,
        "mean_reversion": mean_rev,
        "momentum": momentum,
        "volatility": volatility,
        "stat_arb": stat_arb,
    }
    combined = weighted_signal_combination(all_signals, STRATEGY_WEIGHTS)

    return {
        "signal": combined["signal"],
        "confidence": round(combined["confidence"] * 100),
        "weighted_score": combined["weighted_score"],
        "ma5": round(safe_float(ma5), 2),
        "ma20": round(safe_float(ma20), 2),
        "ma60": round(safe_float(ma60), 2),
        "strategies": {
            "trend_following": {
                "signal": trend["signal"],
                "confidence": round(trend["confidence"] * 100),
                "metrics": trend["metrics"],
            },
            "mean_reversion": {
                "signal": mean_rev["signal"],
                "confidence": round(mean_rev["confidence"] * 100),
                "metrics": mean_rev["metrics"],
            },
            "momentum": {
                "signal": momentum["signal"],
                "confidence": round(momentum["confidence"] * 100),
                "metrics": momentum["metrics"],
            },
            "volatility": {
                "signal": volatility["signal"],
                "confidence": round(volatility["confidence"] * 100),
                "metrics": volatility["metrics"],
            },
            "statistical_arbitrage": {
                "signal": stat_arb["signal"],
                "confidence": round(stat_arb["confidence"] * 100),
                "metrics": stat_arb["metrics"],
            },
        },
    }
