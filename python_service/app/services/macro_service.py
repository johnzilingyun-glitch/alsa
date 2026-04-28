import akshare as ak
import pandas as pd
from typing import Dict, Any
from ..utils.network import safe_ak_call

class MacroService:
    def __init__(self):
        self._cache = {}

    async def get_latest_fx(self) -> Dict[str, float]:
        """
        Fetch latest major FX rates (USD/CNY, etc.)
        """
        try:
            # Using spot quote for major pairs
            df = await safe_ak_call(ak.fx_spot_quote)
            if df is not None and not df.empty:
                # Robust search by row content since column names might be garbled (UTF-8/GBK issues)
                for i in range(len(df)):
                    row_vals = [str(v) for v in df.iloc[i].values]
                    # Check for USD/CNY in the first column
                    if 'USD/CNY' in row_vals[0] or '美元人民币' in row_vals[0]:
                        try:
                            # Usually index 1 is the rate
                            rate = float(df.iloc[i].values[1])
                            if 5.0 < rate < 9.0: # Sanity check for USD/CNY
                                return {
                                    "USD/CNY": rate,
                                    "Source": "CFETS Spot",
                                    "Date": "Real-time"
                                }
                        except:
                            continue
        except Exception as e:
            print(f"FX Primary fetch failed: {e}")
        
        # Fallback to BOC or other stable sources if above fails
        try:
            # Try a very stable EM source if possible
            df = await safe_ak_call(ak.fx_cny_quote)
            if df is not None and not df.empty:
                usd = df[df['币种'].str.contains('美元')]
                if not usd.empty:
                    return {
                        "USD/CNY": float(usd.iloc[0]['中间价']),
                        "Source": "CFETS Fix",
                        "Date": "Today"
                    }
        except:
            pass

        # If all else fails, use a more current estimate for 2026 (based on search)
        return {"USD/CNY": 6.86, "Note": "Fallback to current 2026-Q2 estimate"}

macro_service = MacroService()
