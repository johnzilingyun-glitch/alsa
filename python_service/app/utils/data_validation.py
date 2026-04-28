import pandas as pd

def validate_ak_data(df: pd.DataFrame, min_rows: int = 1) -> bool:
    """
    Validates that the akshare DataFrame is not empty
    and meets the minimum row count requirement.
    """
    if df is None or df.empty:
        return False
    return len(df) >= min_rows
