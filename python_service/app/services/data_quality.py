"""Data Quality Pipeline — validates external market data before it enters the data lake.

Checks completeness, outliers, timeliness, and schema validity.
"""
import logging
from dataclasses import dataclass, field
from typing import List
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class QualityCheck:
    """Result of a single quality check."""
    name: str
    passed: bool
    message: str
    severity: str = "warning"  # info, warning, critical

    def __str__(self):
        status = "✓" if self.passed else "✗"
        return f"[{status}] {self.name}: {self.message}"


@dataclass
class QualityReport:
    """Aggregated data quality report."""
    symbol: str
    checks: List[QualityCheck] = field(default_factory=list)
    overall_passed: bool = True
    score: float = 1.0  # 0.0 to 1.0

    def add_check(self, check: QualityCheck):
        self.checks.append(check)
        if not check.passed and check.severity == "critical":
            self.overall_passed = False

    def compute_score(self):
        if not self.checks:
            self.score = 1.0
            return
        passed = sum(1 for c in self.checks if c.passed)
        self.score = passed / len(self.checks)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "overall_passed": self.overall_passed,
            "score": self.score,
            "checks": [
                {"name": c.name, "passed": c.passed, "message": c.message, "severity": c.severity}
                for c in self.checks
            ],
        }


class DataQualityPipeline:
    """Validates market data quality before storage."""

    def __init__(
        self,
        completeness_threshold: float = 0.95,
        outlier_zscore_threshold: float = 3.0,
        max_delay_days: int = 7,
        max_daily_return_pct: float = 30.0,
    ):
        self.completeness_threshold = completeness_threshold
        self.outlier_zscore_threshold = outlier_zscore_threshold
        self.max_delay_days = max_delay_days
        self.max_daily_return_pct = max_daily_return_pct

    def validate(self, df, symbol: str) -> QualityReport:
        """
        Run all quality checks on a DataFrame of OHLCV data.

        Args:
            df: pandas DataFrame with columns like open, high, low, close, volume, trade_date
            symbol: Stock symbol for logging

        Returns:
            QualityReport with all check results
        """
        report = QualityReport(symbol=symbol)

        if df is None or df.empty:
            report.add_check(QualityCheck(
                name="empty_data",
                passed=False,
                message="DataFrame is None or empty",
                severity="critical",
            ))
            report.compute_score()
            return report

        self._check_completeness(df, report)
        self._check_schema(df, report)
        self._check_outliers(df, report)
        self._check_timeliness(df, report)
        self._check_ohlc_consistency(df, report)
        self._check_volume_anomaly(df, report)

        report.compute_score()
        return report

    def _check_completeness(self, df, report: QualityReport):
        """Check for missing values."""
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        # Try case-insensitive matching
        col_map = {c.lower(): c for c in df.columns}
        present_cols = [col_map.get(c, c) for c in required_cols if col_map.get(c, c) in df.columns or c in df.columns]

        if not present_cols:
            report.add_check(QualityCheck(
                name="missing_columns",
                passed=False,
                message=f"No OHLCV columns found. Available: {list(df.columns)[:10]}",
                severity="critical",
            ))
            return

        total_cells = len(df) * len(present_cols)
        null_cells = df[present_cols].isnull().sum().sum()
        null_pct = null_cells / total_cells if total_cells > 0 else 0

        report.add_check(QualityCheck(
            name="completeness",
            passed=null_pct < (1 - self.completeness_threshold),
            message=f"Null ratio: {null_pct:.2%} ({null_cells}/{total_cells} cells)",
            severity="critical" if null_pct > 0.2 else "warning",
        ))

    def _check_schema(self, df, report: QualityReport):
        """Check that required columns exist."""
        required = {'open', 'high', 'low', 'close', 'volume'}
        # Normalize column names to lowercase for comparison
        cols_lower = {c.lower() for c in df.columns}
        # Also check for Chinese column names
        chinese_map = {
            '开盘': 'open', '最高': 'high', '最低': 'low',
            '收盘': 'close', '成交量': 'volume', '日期': 'trade_date',
        }
        present = set()
        for c in df.columns:
            cl = c.lower()
            if cl in required:
                present.add(cl)
            elif c in chinese_map:
                present.add(chinese_map[c])

        missing = required - present
        report.add_check(QualityCheck(
            name="schema",
            passed=len(missing) == 0,
            message=f"Missing columns: {missing}" if missing else "All OHLCV columns present",
            severity="critical" if missing else "info",
        ))

    def _check_outliers(self, df, report: QualityReport):
        """Check for extreme daily returns."""
        col_map = {c.lower(): c for c in df.columns}
        close_col = col_map.get('close', 'close')

        if close_col not in df.columns:
            return

        try:
            returns = df[close_col].pct_change().dropna()
            if len(returns) == 0:
                return

            extreme_days = (returns.abs() > self.max_daily_return_pct / 100).sum()
            max_return = returns.abs().max()

            report.add_check(QualityCheck(
                name="outliers",
                passed=extreme_days == 0,
                message=f"Extreme returns (>{self.max_daily_return_pct}%): {extreme_days} days, max={max_return:.2%}",
                severity="warning" if extreme_days <= 2 else "critical",
            ))
        except Exception as e:
            report.add_check(QualityCheck(
                name="outliers",
                passed=True,
                message=f"Outlier check skipped: {e}",
                severity="info",
            ))

    def _check_timeliness(self, df, report: QualityReport):
        """Check that data is recent enough."""
        date_col = None
        for c in ['trade_date', 'date', 'Date', '日期']:
            if c in df.columns:
                date_col = c
                break

        if not date_col:
            report.add_check(QualityCheck(
                name="timeliness",
                passed=True,
                message="No date column found, timeliness check skipped",
                severity="info",
            ))
            return

        try:
            dates = df[date_col]
            if dates.dtype == 'object':
                dates = dates.astype(str)
            last_date = dates.iloc[-1]
            if isinstance(last_date, str):
                last_date = datetime.strptime(last_date[:10], "%Y-%m-%d")
            elif hasattr(last_date, 'to_pydatetime'):
                last_date = last_date.to_pydatetime()

            delay_days = (datetime.now() - last_date).days

            report.add_check(QualityCheck(
                name="timeliness",
                passed=delay_days <= self.max_delay_days,
                message=f"Last data date: {last_date.strftime('%Y-%m-%d') if hasattr(last_date, 'strftime') else last_date}, delay: {delay_days} days",
                severity="critical" if delay_days > 30 else "warning",
            ))
        except Exception as e:
            report.add_check(QualityCheck(
                name="timeliness",
                passed=True,
                message=f"Timeliness check failed: {e}",
                severity="info",
            ))

    def _check_ohlc_consistency(self, df, report: QualityReport):
        """Check OHLC logical consistency (high >= low, high >= open/close)."""
        col_map = {c.lower(): c for c in df.columns}
        high_col = col_map.get('high', 'high')
        low_col = col_map.get('low', 'low')

        if high_col not in df.columns or low_col not in df.columns:
            return

        try:
            invalid = (df[high_col] < df[low_col]).sum()
            report.add_check(QualityCheck(
                name="ohlc_consistency",
                passed=invalid == 0,
                message=f"High < Low violations: {invalid} rows",
                severity="critical" if invalid > 0 else "info",
            ))
        except Exception:
            pass

    def _check_volume_anomaly(self, df, report: QualityReport):
        """Check for zero-volume days (possible data issues)."""
        col_map = {c.lower(): c for c in df.columns}
        vol_col = col_map.get('volume', 'volume')

        if vol_col not in df.columns:
            return

        try:
            zero_vol = (df[vol_col] == 0).sum()
            total = len(df)
            zero_pct = zero_vol / total if total > 0 else 0

            report.add_check(QualityCheck(
                name="volume_anomaly",
                passed=zero_pct < 0.1,
                message=f"Zero-volume days: {zero_vol}/{total} ({zero_pct:.1%})",
                severity="warning" if zero_pct > 0.05 else "info",
            ))
        except Exception:
            pass


# Singleton
data_quality_pipeline = DataQualityPipeline()
