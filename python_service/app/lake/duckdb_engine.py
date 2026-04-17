import duckdb
from typing import Dict, Any

class DuckDBMarketQuery:
    def __init__(self):
        # We use a memory connection for ephemeral analytical operations
        self.con = duckdb.connect(database=':memory:')

    def latest_close(self, parquet_glob: str) -> Dict[str, Any]:
        """
        Query the latest close price from the Parquet data lake.
        """
        try:
            # Note: handle cases where glob has no files
            sql = f"""
                SELECT close 
                FROM read_parquet('{parquet_glob}') 
                ORDER BY trade_date DESC 
                LIMIT 1
            """
            result = self.con.execute(sql).df()
            if result.empty:
                return {}
            return {"close": float(result.iloc[0]['close'])}
        except Exception as e:
            print(f"DuckDB query failed: {e}")
            return {}

    def run_query(self, sql: str) -> Any:
        return self.con.execute(sql).df()
