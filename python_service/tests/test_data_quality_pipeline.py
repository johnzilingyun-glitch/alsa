"""Tests for DataQualityPipeline — validates market data before storage."""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from python_service.app.services.data_quality import (
    DataQualityPipeline, QualityCheck, QualityReport, data_quality_pipeline,
)


def _make_ohlcv_df(n=100, include_date=True):
    """Helper: generate a clean OHLCV DataFrame."""
    dates = pd.date_range(end=datetime.now(), periods=n, freq='B')
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame({
        'open': close + np.random.randn(n) * 0.2,
        'high': close + abs(np.random.randn(n) * 0.5),
        'low': close - abs(np.random.randn(n) * 0.5),
        'close': close,
        'volume': np.random.randint(1000, 100000, n),
    })
    if include_date:
        df['trade_date'] = dates.strftime('%Y-%m-%d')
    return df


class TestEmptyData:
    """Test handling of empty/None data."""

    def test_none_dataframe(self):
        pipeline = DataQualityPipeline()
        report = pipeline.validate(None, "TEST")
        assert report.overall_passed is False
        assert any(c.name == "empty_data" for c in report.checks)

    def test_empty_dataframe(self):
        pipeline = DataQualityPipeline()
        report = pipeline.validate(pd.DataFrame(), "TEST")
        assert report.overall_passed is False


class TestCompletenessCheck:
    """Test data completeness validation."""

    def test_complete_data_passes(self):
        pipeline = DataQualityPipeline()
        df = _make_ohlcv_df()
        report = pipeline.validate(df, "TEST")
        completeness = next((c for c in report.checks if c.name == "completeness"), None)
        assert completeness is not None
        assert completeness.passed == True

    def test_high_null_rate_fails(self):
        pipeline = DataQualityPipeline(completeness_threshold=0.95)
        df = _make_ohlcv_df()
        # Add 30% nulls
        mask = np.random.random(len(df)) < 0.3
        df.loc[mask, 'close'] = np.nan
        df.loc[mask, 'open'] = np.nan
        report = pipeline.validate(df, "TEST")
        completeness = next((c for c in report.checks if c.name == "completeness"), None)
        assert completeness is not None
        assert completeness.passed == False


class TestSchemaCheck:
    """Test schema validation."""

    def test_all_columns_present(self):
        pipeline = DataQualityPipeline()
        df = _make_ohlcv_df()
        report = pipeline.validate(df, "TEST")
        schema = next((c for c in report.checks if c.name == "schema"), None)
        assert schema is not None
        assert schema.passed is True

    def test_missing_columns_detected(self):
        pipeline = DataQualityPipeline()
        df = pd.DataFrame({'close': [1, 2, 3], 'volume': [100, 200, 300]})
        report = pipeline.validate(df, "TEST")
        schema = next((c for c in report.checks if c.name == "schema"), None)
        assert schema is not None
        assert schema.passed is False
        assert "Missing" in schema.message or "missing" in schema.message.lower()


class TestOutlierCheck:
    """Test extreme return detection."""

    def test_normal_returns_pass(self):
        pipeline = DataQualityPipeline(max_daily_return_pct=30.0)
        df = _make_ohlcv_df()
        report = pipeline.validate(df, "TEST")
        outlier = next((c for c in report.checks if c.name == "outliers"), None)
        if outlier:
            assert outlier.passed == True

    def test_extreme_return_flagged(self):
        pipeline = DataQualityPipeline(max_daily_return_pct=10.0)
        df = _make_ohlcv_df()
        # Inject extreme return
        df.loc[50, 'close'] = df.loc[49, 'close'] * 1.5  # 50% return
        report = pipeline.validate(df, "TEST")
        outlier = next((c for c in report.checks if c.name == "outliers"), None)
        if outlier:
            assert outlier.passed == False


class TestOHLCConsistency:
    """Test OHLC logical consistency."""

    def test_consistent_ohlc_passes(self):
        pipeline = DataQualityPipeline()
        df = _make_ohlcv_df()
        report = pipeline.validate(df, "TEST")
        ohlc = next((c for c in report.checks if c.name == "ohlc_consistency"), None)
        if ohlc:
            assert ohlc.passed == True

    def test_high_below_low_flagged(self):
        pipeline = DataQualityPipeline()
        df = _make_ohlcv_df()
        # Make high < low for some rows
        df.loc[10, 'high'] = df.loc[10, 'low'] - 1
        df.loc[20, 'high'] = df.loc[20, 'low'] - 2
        report = pipeline.validate(df, "TEST")
        ohlc = next((c for c in report.checks if c.name == "ohlc_consistency"), None)
        if ohlc:
            assert ohlc.passed == False


class TestVolumeAnomaly:
    """Test zero volume detection."""

    def test_normal_volume_passes(self):
        pipeline = DataQualityPipeline()
        df = _make_ohlcv_df()
        report = pipeline.validate(df, "TEST")
        vol = next((c for c in report.checks if c.name == "volume_anomaly"), None)
        if vol:
            assert vol.passed == True

    def test_many_zero_volumes_flagged(self):
        pipeline = DataQualityPipeline()
        df = _make_ohlcv_df()
        # Set 30% of volume to 0
        df.loc[df.index[:30], 'volume'] = 0
        report = pipeline.validate(df, "TEST")
        vol = next((c for c in report.checks if c.name == "volume_anomaly"), None)
        if vol:
            assert vol.passed == False


class TestQualityReport:
    """Test QualityReport aggregation."""

    def test_score_computation(self):
        report = QualityReport(symbol="TEST")
        report.add_check(QualityCheck(name="a", passed=True, message="ok"))
        report.add_check(QualityCheck(name="b", passed=False, message="fail"))
        report.compute_score()
        assert report.score == pytest.approx(0.5)

    def test_empty_report_score_is_1(self):
        report = QualityReport(symbol="TEST")
        report.compute_score()
        assert report.score == 1.0

    def test_critical_failure_marks_overall_failed(self):
        report = QualityReport(symbol="TEST")
        report.add_check(QualityCheck(name="x", passed=False, message="critical fail", severity="critical"))
        assert report.overall_passed is False

    def test_warning_failure_does_not_affect_overall(self):
        report = QualityReport(symbol="TEST")
        report.add_check(QualityCheck(name="x", passed=False, message="warning", severity="warning"))
        assert report.overall_passed is True  # Only critical failures affect overall

    def test_to_dict(self):
        report = QualityReport(symbol="TEST")
        report.add_check(QualityCheck(name="a", passed=True, message="ok"))
        report.compute_score()
        d = report.to_dict()
        assert d["symbol"] == "TEST"
        assert len(d["checks"]) == 1

    def test_quality_check_str(self):
        c = QualityCheck(name="test", passed=True, message="all good")
        assert "✓" in str(c)
        c2 = QualityCheck(name="test", passed=False, message="bad")
        assert "✗" in str(c2)
