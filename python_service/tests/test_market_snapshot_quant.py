import os
import sys
import warnings

import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from python_service.app.services.market_snapshot_service import MarketSnapshotService


def test_constant_price_hurst_defaults_without_runtime_warning():
    frame = pd.DataFrame(
        {
            "close": [10.0] * 60,
            "high": [11.0] * 60,
            "low": [9.0] * 60,
        }
    )

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        result = MarketSnapshotService._compute_quant_ensemble(frame)

    assert result["indicators"]["Hurst"] == 0.5
    assert not any("divide by zero" in str(warning.message).lower() for warning in captured)
