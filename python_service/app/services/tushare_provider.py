import os
import tushare as ts
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class TushareDataProvider:
    def __init__(self, token=None):
        self.token = token or os.getenv("TUSHARE_API_TOKEN")
        if self.token:
            ts.set_token(self.token)
            self.client = ts.pro_api()
        else:
            logger.warning("TUSHARE_API_TOKEN is not set. Tushare provider will not function correctly.")
            self.client = None
    
    def get_financials(self, symbol: str) -> pd.DataFrame:
        """
        Fetch and merge income, balancesheet, and cashflow data for a given ts_code.
        Returns a unified DataFrame.
        """
        if not self.client:
            logger.error("Cannot fetch financials: Tushare API client not initialized.")
            return pd.DataFrame()
            
        try:
            # Note: tushare ts_code format is usually "000001.SZ"
            income = self.client.income(ts_code=symbol, limit=10)
            balance = self.client.balancesheet(ts_code=symbol, limit=10)
            cashflow = self.client.cashflow(ts_code=symbol, limit=10)
            
            # Merge logic. They share 'end_date' and 'ts_code' as keys.
            if income.empty and balance.empty and cashflow.empty:
                return pd.DataFrame()
                
            merged = income
            if not balance.empty:
                merged = pd.merge(merged, balance, on=['ts_code', 'end_date', 'ann_date'], how='outer', suffixes=('', '_bal'))
            if not cashflow.empty:
                merged = pd.merge(merged, cashflow, on=['ts_code', 'end_date', 'ann_date'], how='outer', suffixes=('', '_cf'))
                
            return merged.drop_duplicates(subset=['end_date']).sort_values('end_date', ascending=False)
            
        except Exception as e:
            logger.error(f"Failed to fetch Tushare financials for {symbol}: {e}", exc_info=True)
            return pd.DataFrame()

# Singleton instance
tushare_provider = TushareDataProvider()
