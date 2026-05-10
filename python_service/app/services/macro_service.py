import akshare as ak
import pandas as pd
from typing import Dict, Any, List
from ..utils.network import safe_ak_call
from datetime import datetime


class MacroService:
    """权威数据源宏观数据服务。使用 AkShare API、CFETS 官方数据，辅以搜索验证。"""

    # 权威商品价格 — 合约代码映射到 AkShare vars_list
    COMMODITY_CODE_MAP = {
        "Lithium Carbonate": "LC",
        "Copper":             "CU",
        "Aluminum":           "AL",
        "Silicon":            "SI",
        "Crude Oil":          "SC",
        "Methanol":           "MA",
        "Polypropylene":      "PP",
        "LLDPE":              "L",
    }
    COMMODITY_UNITS = {
        "Lithium Carbonate": "元/吨",
        "Copper":             "元/吨",
        "Aluminum":           "元/吨",
        "Silicon":            "元/吨",
        "Crude Oil":          "元/桶",
        "Methanol":           "元/吨",
        "Polypropylene":      "元/吨",
        "LLDPE":              "元/吨",
    }
    COMMODITY_SOURCE = "期货交易所现货报价 (AkShare)"

    def __init__(self):
        self._cache = {}

    async def get_latest_fx(self) -> Dict[str, Any]:
        """获取最新 USD/CNY 汇率。仅使用 CFETS 官方数据。"""
        if "fx_rate" in self._cache:
            return self._cache["fx_rate"]

        # 优先: CFETS 即期报价
        try:
            df = await safe_ak_call(ak.fx_spot_quote)
            if df is not None and not df.empty:
                for i in range(len(df)):
                    row_vals = [str(v) for v in df.iloc[i].values]
                    if "USD/CNY" in row_vals[0] or "美元人民币" in row_vals[0]:
                        try:
                            rate = float(df.iloc[i].values[1])
                            if 5.0 < rate < 9.0:
                                res = {
                                    "USD/CNY": rate,
                                    "Source": "CFETS Spot (中国外汇交易中心)",
                                    "Date": datetime.now().strftime("%Y-%m-%d"),
                                }
                                self._cache["fx_rate"] = res
                                return res
                        except (ValueError, IndexError):
                            continue
        except Exception as e:
            print(f"FX CFETS Spot failed: {e}")

        # 备选: CFETS 中间价
        try:
            df = await safe_ak_call(ak.fx_cny_quote)
            if df is not None and not df.empty:
                usd = df[df["币种"].str.contains("美元")]
                if not usd.empty:
                    res = {
                        "USD/CNY": float(usd.iloc[0]["中间价"]),
                        "Source": "CFETS Fix (中国外汇交易中心中间价)",
                        "Date": datetime.now().strftime("%Y-%m-%d"),
                    }
                    self._cache["fx_rate"] = res
                    return res
        except Exception as e:
            print(f"FX CFETS Fix failed: {e}")

        # 数据源全部失败，使用 yfinance 作为最终回退
        try:
            import yfinance as yf
            fx_ticker = yf.Ticker("USDCNY=X")
            fx_info = fx_ticker.info
            yf_rate = fx_info.get("regularMarketPrice")
            if yf_rate and 5.0 < yf_rate < 9.0:
                res = {
                    "USD/CNY": yf_rate,
                    "Source": "Yahoo Finance (yfinance USDCNY=X)",
                    "Date": datetime.now().strftime("%Y-%m-%d"),
                }
                self._cache["fx_rate"] = res
                return res
        except Exception as e:
            print(f"FX yfinance fallback failed: {e}")

        # 所有数据源全部失败，返回 None
        res = {
            "USD/CNY": None,
            "Source": "N/A",
            "Note": "权威数据源(CFETS/yfinance)暂不可用。请基于 [API DATA / MARKET SNAPSHOT] 中的数据进行判断，禁止使用训练数据中的过期汇率。",
        }
        self._cache["fx_rate"] = res
        return res

    async def get_commodity_prices(self, symbols: list = None) -> Dict[str, Any]:
        """获取大宗商品现货价格。仅使用交易所官方数据，不使用搜索。"""
        if not symbols:
            symbols = ["Lithium Carbonate", "Copper"]

        results = {}
        for sym in symbols:
            cache_key = f"comm_{sym}"
            if cache_key in self._cache:
                results[sym] = self._cache[cache_key]
                continue

            result = await self._fetch_commodity(sym)
            self._cache[cache_key] = result
            results[sym] = result

        return results

    async def _fetch_commodity(self, symbol: str) -> Dict[str, Any]:
        """通过 AkShare futures_spot_price 获取交易所现货报价。"""
        code = self.COMMODITY_CODE_MAP.get(symbol)
        unit = self.COMMODITY_UNITS.get(symbol, "")
        if not code:
            return {"error": f"不支持的商品: {symbol}", "symbol": symbol}

        # 方案1: 期货交易所现货报价 (主力)
        try:
            today = datetime.now().strftime("%Y%m%d")
            df = await safe_ak_call(ak.futures_spot_price, date=today, vars_list=[code])
            if df is not None and not df.empty:
                row = df[df["symbol"] == code]
                if not row.empty:
                    r = row.iloc[0]
                    price = float(r["spot_price"]) if pd.notna(r.get("spot_price")) else None
                    if price is not None and price > 0:
                        return {
                            "symbol": symbol,
                            "price": price,
                            "unit": unit,
                            "source": self.COMMODITY_SOURCE,
                            "date": str(r.get("date", today)),
                        }
        except Exception as e:
            print(f"AkShare futures_spot_price failed for {symbol}: {e}")

        # 方案2: 备选日期 (非交易日时今日可能无数据，回退至多 10 天覆盖长假)
        import datetime as dt
        for days_back in range(1, 11):
            try:
                back_date = (dt.datetime.now() - dt.timedelta(days=days_back)).strftime("%Y%m%d")
                df = await safe_ak_call(ak.futures_spot_price, date=back_date, vars_list=[code])
                if df is not None and not df.empty:
                    row = df[df["symbol"] == code]
                    if not row.empty:
                        r = row.iloc[0]
                        price = float(r["spot_price"]) if pd.notna(r.get("spot_price")) else None
                        if price is not None and price > 0:
                            return {
                                "symbol": symbol,
                                "price": price,
                                "unit": unit,
                                "source": self.COMMODITY_SOURCE,
                                "date": str(r.get("date", back_date)),
                            }
            except Exception:
                continue

        # 全部失败
        return {
            "symbol": symbol,
            "price": None,
            "unit": unit,
            "source": "N/A",
            "error": "权威数据源(期货交易所)暂不可用。请勿使用搜索或训练数据中的过期价格。",
        }

    async def get_brent_oil_price(self) -> Dict[str, Any]:
        """获取布伦特原油现货价格 (美元/桶)。"""
        if "brent" in self._cache:
            return self._cache["brent"]

        # Plan A: AkShare 期货外盘 (Brent)
        try:
            df = await safe_ak_call(ak.futures_foreign_hist, symbol="布伦特原油")
            if df is not None and not df.empty:
                last_row = df.iloc[-1]
                price = float(last_row.get("收盘") or last_row.get("close"))
                date_val = str(last_row.get("日期") or last_row.get("date", ""))
                result = {
                    "symbol": "Brent Crude Oil",
                    "price": price,
                    "unit": "美元/桶",
                    "source": "ICE 期货交易所 (AkShare)",
                    "date": date_val
                }
                self._cache["brent"] = result
                return result
        except Exception as e:
            print(f"Brent oil AkShare failed: {e}")

        # Plan B: AkShare 国际原油 WTI (对照参考)
        try:
            df = await safe_ak_call(ak.futures_foreign_hist, symbol="WTI原油")
            if df is not None and not df.empty:
                last_row = df.iloc[-1]
                price = float(last_row.get("收盘") or last_row.get("close"))
                date_val = str(last_row.get("日期") or last_row.get("date", ""))
                result = {
                    "symbol": "WTI Crude Oil (参考)",
                    "price": price,
                    "unit": "美元/桶",
                    "source": "NYMEX 期货交易所 (AkShare)",
                    "date": date_val,
                    "note": "布伦特数据不可用，使用WTI作为参考。布伦特通常比WTI高2-5美元。"
                }
                self._cache["brent"] = result
                return result
        except Exception as e:
            print(f"WTI oil AkShare failed: {e}")

        result = {
            "symbol": "Brent Crude Oil",
            "price": None, "unit": "美元/桶", "source": "N/A",
            "error": "原油价格数据暂不可用。禁止估算或使用训练数据。"
        }
        self._cache["brent"] = result
        return result

    async def get_macro_indicators(self) -> Dict[str, Any]:
        """获取关键宏观经济指标：M2、LPR、美联储利率。"""
        if "macro_indicators" in self._cache:
            return self._cache["macro_indicators"]

        indicators = {}

        # 1. M2 货币供应量 (AkShare)
        try:
            df = await safe_ak_call(ak.macro_china_money_supply)
            if df is not None and not df.empty:
                last = df.iloc[0]
                m2_val = last.get("M2-数量(亿元)") or last.get("M2数量(亿元)")
                m2_yoy = last.get("M2-同比增长") or last.get("M2同比增长")
                date_val = str(last.get("月份", ""))
                indicators["M2"] = {
                    "value": m2_val,
                    "yoy": m2_yoy,
                    "unit": "亿元",
                    "source": "中国人民银行 (AkShare)",
                    "date": date_val
                }
        except Exception as e:
            print(f"M2 data fetch failed: {e}")
            indicators["M2"] = {"value": None, "error": "数据暂不可用"}

        # 2. LPR 利率 (AkShare)
        try:
            df = await safe_ak_call(ak.macro_china_lpr)
            if df is not None and not df.empty:
                last = df.iloc[-1]
                indicators["LPR"] = {
                    "1y": last.get("LPR1Y") or last.get("1年"),
                    "5y": last.get("LPR5Y") or last.get("5年"),
                    "source": "中国人民银行 (AkShare)",
                    "date": str(last.get("TRADE_DATE", "") or last.get("日期", ""))
                }
        except Exception as e:
            print(f"LPR data fetch failed: {e}")
            indicators["LPR"] = {"1y": None, "5y": None, "error": "数据暂不可用"}

        # 3. 美联储联邦基金利率 (AkShare)
        try:
            df = await safe_ak_call(ak.macro_bank_usa_interest_rate)
            if df is not None and not df.empty:
                last = df.iloc[-1]
                indicators["FedRate"] = {
                    "rate": last.get("今值") or last.get("利率"),
                    "source": "Federal Reserve (AkShare)",
                    "date": str(last.get("日期", ""))
                }
        except Exception as e:
            print(f"Fed rate fetch failed: {e}")
            indicators["FedRate"] = {"rate": None, "error": "数据暂不可用"}

        self._cache["macro_indicators"] = indicators
        return indicators


macro_service = MacroService()
