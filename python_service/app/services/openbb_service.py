"""
OpenBB Data Service — Provides additional financial data via OpenBB Platform.

Free providers used (no API key required):
  - yfinance: fundamentals (income/balance/cash/metrics), analyst consensus, company news
  - sec: SEC filings (10-K/10-Q/8-K), insider trading
  - oecd/econdb/imf: macro economic data (CPI, GDP)

Complements AkShare (A-Share) and yfinance (US/HK) with:
  - SEC filings & insider trading
  - Analyst consensus & estimates
  - Key financial metrics/ratios
  - Macro economic data
"""

import asyncio
from typing import Optional


def _safe_val(v, precision: int = 2) -> str:
    """Format a value safely for display."""
    if v is None or (isinstance(v, float) and v != v):
        return "N/A"
    if isinstance(v, float):
        if abs(v) >= 1e9:
            return f"{v/1e9:.{precision}f}B"
        if abs(v) >= 1e6:
            return f"{v/1e6:.{precision}f}M"
        if abs(v) < 0.01 and v != 0:
            return f"{v:.4f}"
        return f"{v:.{precision}f}"
    return str(v)


class OpenBBService:
    """Wraps OpenBB Platform calls with error handling and result formatting."""

    def __init__(self):
        self._obb = None

    @property
    def obb(self):
        if self._obb is None:
            from openbb import obb
            self._obb = obb
        return self._obb

    async def get_analyst_consensus(self, symbol: str) -> str:
        """Get analyst consensus (target price, recommendation) via yfinance."""
        try:
            loop = asyncio.get_event_loop()
            r = await loop.run_in_executor(
                None,
                lambda: self.obb.equity.estimates.consensus(symbol, provider="yfinance")
            )
            df = r.to_df()
            if df.empty:
                return ""
            row = df.iloc[0]
            lines = ["## Analyst Consensus (OpenBB/yfinance)"]
            fields = {
                "target_high": "Target High",
                "target_low": "Target Low",
                "target_consensus": "Target Consensus",
                "target_median": "Target Median",
                "recommendation": "Recommendation",
                "number_of_analysts": "# Analysts",
                "current_price": "Current Price",
            }
            for col, label in fields.items():
                val = row.get(col) if col in row.index else None
                if val is not None and str(val) != "nan":
                    lines.append(f"- {label}: {_safe_val(val)}")
            lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return f"⚠ Analyst consensus failed: {e}"

    async def get_key_metrics(self, symbol: str) -> str:
        """Get key financial metrics/ratios via yfinance."""
        try:
            loop = asyncio.get_event_loop()
            r = await loop.run_in_executor(
                None,
                lambda: self.obb.equity.fundamental.metrics(symbol, provider="yfinance")
            )
            df = r.to_df()
            if df.empty:
                return ""
            row = df.iloc[0]
            lines = ["## Key Metrics (OpenBB/yfinance)"]
            fields = {
                "pe_ratio": "P/E Ratio",
                "forward_pe": "Forward P/E",
                "peg_ratio": "PEG Ratio",
                "price_to_book": "P/B Ratio",
                "enterprise_to_ebitda": "EV/EBITDA",
                "enterprise_to_revenue": "EV/Revenue",
                "quick_ratio": "Quick Ratio",
                "current_ratio": "Current Ratio",
                "debt_to_equity": "Debt/Equity",
                "gross_margin": "Gross Margin",
                "operating_margin": "Operating Margin",
                "profit_margin": "Net Margin",
                "return_on_equity": "ROE",
                "return_on_assets": "ROA",
                "earnings_growth": "Earnings Growth",
                "earnings_growth_quarterly": "EPS Growth (Q)",
                "revenue_growth": "Revenue Growth",
                "dividend_yield": "Dividend Yield",
                "payout_ratio": "Payout Ratio",
                "beta": "Beta",
            }
            for col, label in fields.items():
                val = row.get(col) if col in row.index else None
                if val is not None and str(val) != "nan":
                    # Format percentages
                    if col in ("gross_margin", "operating_margin", "profit_margin",
                               "return_on_equity", "return_on_assets",
                               "earnings_growth", "earnings_growth_quarterly",
                               "revenue_growth", "payout_ratio"):
                        if isinstance(val, (int, float)) and abs(val) < 10:
                            lines.append(f"- {label}: {val*100:.1f}%")
                            continue
                    lines.append(f"- {label}: {_safe_val(val)}")
            lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return f"⚠ Key metrics failed: {e}"

    async def get_sec_filings(self, symbol: str, filing_type: Optional[str] = None, limit: int = 5) -> str:
        """Get SEC filings (10-K, 10-Q, 8-K, etc.)."""
        try:
            loop = asyncio.get_event_loop()
            kwargs = {"symbol": symbol, "provider": "sec", "limit": limit}
            if filing_type:
                kwargs["type"] = filing_type
            r = await loop.run_in_executor(
                None,
                lambda: self.obb.equity.fundamental.filings(**kwargs)
            )
            df = r.to_df()
            if df.empty:
                return ""
            lines = [f"## SEC Filings (OpenBB/SEC){' — ' + filing_type if filing_type else ''}"]
            for _, row in df.iterrows():
                ftype = row.get("report_type", "N/A")
                fdate = str(row.get("filing_date", "N/A"))[:10]
                url = row.get("report_url", "")
                rdate = str(row.get("report_date", ""))[:10] if row.get("report_date") else ""
                desc = f"  Report date: {rdate}" if rdate and rdate not in ("NaT", "nan", "") else ""
                lines.append(f"- [{fdate}] {ftype}{desc}")
                if url:
                    lines.append(f"  URL: {url}")
            lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return f"⚠ SEC filings failed: {e}"

    async def get_insider_trading(self, symbol: str, limit: int = 10) -> str:
        """Get insider trading data from SEC."""
        try:
            loop = asyncio.get_event_loop()
            r = await loop.run_in_executor(
                None,
                lambda: self.obb.equity.ownership.insider_trading(
                    symbol, provider="sec", limit=limit
                )
            )
            df = r.to_df()
            if df.empty:
                return ""
            lines = ["## Insider Trading (OpenBB/SEC)"]
            for _, row in df.iterrows():
                date = str(row.get("transaction_date", row.get("filing_date", "N/A")))[:10]
                name = row.get("owner_name", "N/A")
                ttype = row.get("acquisition_or_disposition", "")
                shares = row.get("securities_transacted", "N/A")
                price = row.get("price", "")
                if str(date) in ("NaT", "nan", "None", "N/A") or not ttype or str(ttype) == "nan":
                    continue
                price_str = f" @ ${_safe_val(price)}" if price and str(price) != "nan" else ""
                lines.append(f"- [{date}] {name}: {ttype} {_safe_val(shares)} shares{price_str}")
            lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return f"⚠ Insider trading failed: {e}"

    async def get_income_statement(self, symbol: str, period: str = "quarter", limit: int = 4) -> str:
        """Get income statement via yfinance (quarterly or annual)."""
        try:
            loop = asyncio.get_event_loop()
            r = await loop.run_in_executor(
                None,
                lambda: self.obb.equity.fundamental.income(
                    symbol, provider="yfinance", period=period, limit=limit
                )
            )
            df = r.to_df()
            if df.empty:
                return ""
            period_label = "Quarterly" if period == "quarter" else "Annual"
            lines = [f"## Income Statement — {period_label} (OpenBB/yfinance)"]
            key_items = [
                ("total_revenue", "Total Revenue"),
                ("cost_of_revenue", "Cost of Revenue"),
                ("gross_profit", "Gross Profit"),
                ("operating_income", "Operating Income"),
                ("net_income", "Net Income"),
                ("ebitda", "EBITDA"),
                ("basic_earnings_per_share", "Basic EPS"),
                ("diluted_earnings_per_share", "Diluted EPS"),
            ]
            for _, row in df.iterrows():
                pe = str(row.get("period_ending", "N/A"))[:10]
                lines.append(f"### {pe}")
                for col, label in key_items:
                    val = row.get(col)
                    if val is not None and str(val) != "nan":
                        lines.append(f"  - {label}: {_safe_val(val)}")
            lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return f"⚠ Income statement failed: {e}"

    async def get_balance_sheet(self, symbol: str, period: str = "quarter", limit: int = 2) -> str:
        """Get balance sheet via yfinance."""
        try:
            loop = asyncio.get_event_loop()
            r = await loop.run_in_executor(
                None,
                lambda: self.obb.equity.fundamental.balance(
                    symbol, provider="yfinance", period=period, limit=limit
                )
            )
            df = r.to_df()
            if df.empty:
                return ""
            period_label = "Quarterly" if period == "quarter" else "Annual"
            lines = [f"## Balance Sheet — {period_label} (OpenBB/yfinance)"]
            key_items = [
                ("total_assets", "Total Assets"),
                ("total_liabilities", "Total Liabilities"),
                ("total_equity", "Total Equity"),
                ("cash_and_cash_equivalents", "Cash & Equivalents"),
                ("total_debt", "Total Debt"),
                ("net_debt", "Net Debt"),
                ("current_assets", "Current Assets"),
                ("current_liabilities", "Current Liabilities"),
                ("inventory", "Inventory"),
            ]
            for _, row in df.iterrows():
                pe = str(row.get("period_ending", "N/A"))[:10]
                lines.append(f"### {pe}")
                for col, label in key_items:
                    val = row.get(col)
                    if val is not None and str(val) != "nan":
                        lines.append(f"  - {label}: {_safe_val(val)}")
            lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return f"⚠ Balance sheet failed: {e}"

    async def get_cash_flow(self, symbol: str, period: str = "quarter", limit: int = 4) -> str:
        """Get cash flow statement via yfinance."""
        try:
            loop = asyncio.get_event_loop()
            r = await loop.run_in_executor(
                None,
                lambda: self.obb.equity.fundamental.cash(
                    symbol, provider="yfinance", period=period, limit=limit
                )
            )
            df = r.to_df()
            if df.empty:
                return ""
            period_label = "Quarterly" if period == "quarter" else "Annual"
            lines = [f"## Cash Flow — {period_label} (OpenBB/yfinance)"]
            key_items = [
                ("operating_cash_flow", "Operating Cash Flow"),
                ("capital_expenditure", "CapEx"),
                ("free_cash_flow", "Free Cash Flow"),
                ("investing_cash_flow", "Investing Cash Flow"),
                ("financing_cash_flow", "Financing Cash Flow"),
            ]
            for _, row in df.iterrows():
                pe = str(row.get("period_ending", "N/A"))[:10]
                lines.append(f"### {pe}")
                for col, label in key_items:
                    val = row.get(col)
                    if val is not None and str(val) != "nan":
                        lines.append(f"  - {label}: {_safe_val(val)}")
            lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return f"⚠ Cash flow failed: {e}"

    async def query(self, symbol: str, query: str) -> str:
        """
        Route a natural language query to appropriate OpenBB endpoints.
        Returns formatted text ready for tool_observation injection.
        """
        query_lower = query.lower()
        results = []
        is_a_share = symbol.isdigit() and len(symbol) == 6

        # Analyst consensus & metrics (US/HK only — A-Share not supported by yfinance OpenBB)
        if not is_a_share:
            if any(kw in query_lower for kw in [
                "analyst", "consensus", "target", "rating", "recommendation",
                "估值", "目标价", "分析师"
            ]):
                results.append(await self.get_analyst_consensus(symbol))

            if any(kw in query_lower for kw in [
                "metric", "ratio", "pe", "pb", "roe", "roa", "margin",
                "valuation", "指标", "估值"
            ]):
                results.append(await self.get_key_metrics(symbol))

            if any(kw in query_lower for kw in [
                "income", "revenue", "earnings", "profit", "eps",
                "利润", "营收", "收入"
            ]):
                results.append(await self.get_income_statement(symbol))

            if any(kw in query_lower for kw in [
                "balance", "asset", "debt", "liability", "cash",
                "资产", "负债", "现金"
            ]):
                results.append(await self.get_balance_sheet(symbol))

            if any(kw in query_lower for kw in [
                "cash flow", "capex", "fcf", "operating cash",
                "现金流", "资本开支"
            ]):
                results.append(await self.get_cash_flow(symbol))

        # SEC filings (US stocks only)
        if not is_a_share and not symbol.endswith(".HK"):
            if any(kw in query_lower for kw in [
                "filing", "sec", "10-k", "10-q", "8-k", "annual report",
                "quarterly report", "报告"
            ]):
                filing_type = None
                if "10-k" in query_lower:
                    filing_type = "10-K"
                elif "10-q" in query_lower:
                    filing_type = "10-Q"
                elif "8-k" in query_lower:
                    filing_type = "8-K"
                results.append(await self.get_sec_filings(symbol, filing_type))

        # Insider trading (US stocks only)
        if not is_a_share and not symbol.endswith(".HK"):
            if any(kw in query_lower for kw in [
                "insider", "insider trading", "management trade",
                "内部交易", "高管交易"
            ]):
                results.append(await self.get_insider_trading(symbol))

        # If no specific query matched, provide a general overview
        if not results and not is_a_share:
            results.append(await self.get_key_metrics(symbol))
            results.append(await self.get_analyst_consensus(symbol))

        # Filter out empty results
        results = [r for r in results if r and r.strip()]
        return "\n".join(results) if results else ""


# Singleton
openbb_service = OpenBBService()
