import duckdb
from typing import Dict, Any
import time

class DuckDBMarketQuery:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DuckDBMarketQuery, cls).__new__(cls)
            # 持久化连接
            cls._instance.con = duckdb.connect(database=':memory:')
            cls._instance._cache = {}
        return cls._instance

    def latest_close(self, parquet_glob: str) -> Dict[str, Any]:
        """
        Query the latest close price with a 30s TTL cache.
        """
        now = time.time()
        cache_key = parquet_glob

        if cache_key in self._cache and (now - self._cache[cache_key]['ts'] < 30):
            return self._cache[cache_key]['data']

        try:
            sql = f"""
                SELECT close
                FROM read_parquet('{parquet_glob}')
                ORDER BY trade_date DESC
                LIMIT 1
            """
            result = self.con.execute(sql).df()

            data = {}
            if not result.empty:
                data = {"close": float(result.iloc[0]['close'])}

            self._cache[cache_key] = {'data': data, 'ts': now}
            return data
        except Exception as e:
            print(f"DuckDB query failed: {e}")
            return {}
