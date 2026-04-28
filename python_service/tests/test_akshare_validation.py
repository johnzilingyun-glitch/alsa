import pandas as pd
import pytest
from python_service.app.utils.data_validation import validate_ak_data

def test_validate_ak_data_empty():
    df = pd.DataFrame()
    assert validate_ak_data(df, min_rows=1) is False

def test_validate_ak_data_insufficient():
    df = pd.DataFrame({'a': [1]})
    assert validate_ak_data(df, min_rows=5) is False

def test_validate_ak_data_valid():
    df = pd.DataFrame({'a': range(10)})
    assert validate_ak_data(df, min_rows=5) is True
