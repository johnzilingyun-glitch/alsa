"""Risk Models — institutional-grade risk metrics and position sizing.

Provides:
- Historical VaR and CVaR (Expected Shortfall)
- Half-Kelly position sizing with Bayesian adjustment
- Maximum drawdown analysis
- Risk-reward ratio calculation
- Portfolio correlation analysis
"""
import numpy as np
import pandas as pd
import logging
from dataclasses import dataclass
from typing import Optional, Dict

logger = logging.getLogger(__name__)


@dataclass
class RiskMetrics:
    """Comprehensive risk metrics for a portfolio or position."""
    var_95: float = 0.0
    var_99: float = 0.0
    cvar_95: float = 0.0
    cvar_99: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration_days: int = 0
    annualized_volatility: float = 0.0
    downside_volatility: float = 0.0
    beta: float = 1.0
    tracking_error: float = 0.0
    information_ratio: float = 0.0

    def to_dict(self) -> dict:
        return {
            "var_95": round(self.var_95, 4),
            "var_99": round(self.var_99, 4),
            "cvar_95": round(self.cvar_95, 4),
            "cvar_99": round(self.cvar_99, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "max_drawdown_duration_days": self.max_drawdown_duration_days,
            "annualized_volatility": round(self.annualized_volatility, 4),
            "downside_volatility": round(self.downside_volatility, 4),
            "beta": round(self.beta, 4),
            "tracking_error": round(self.tracking_error, 4),
            "information_ratio": round(self.information_ratio, 4),
        }


class RiskModels:
    """Institutional-grade risk calculation models."""

    def historical_var(self, returns: np.ndarray, confidence: float = 0.95, holding_period: int = 1) -> float:
        """
        Historical Simulation VaR.
        
        Args:
            returns: Array of historical returns
            confidence: Confidence level (e.g., 0.95 for 95%)
            holding_period: Holding period in days
            
        Returns:
            Value at Risk (positive number representing potential loss)
        """
        if len(returns) == 0:
            return 0.0
        sorted_returns = np.sort(returns)
        index = int((1 - confidence) * len(sorted_returns))
        index = max(0, min(index, len(sorted_returns) - 1))
        return -sorted_returns[index] * np.sqrt(holding_period)

    def cvar(self, returns: np.ndarray, confidence: float = 0.95) -> float:
        """
        Conditional VaR (Expected Shortfall).
        
        The expected loss given that the loss exceeds VaR.
        More conservative than VaR — captures tail risk.
        """
        if len(returns) == 0:
            return 0.0
        var = self.historical_var(returns, confidence)
        tail_returns = returns[returns <= -var]
        if len(tail_returns) == 0:
            return var
        return -np.mean(tail_returns)

    def kelly_criterion(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        fraction: float = 0.5,
        min_kelly: float = 0.0,
        max_kelly: float = 0.25,
    ) -> Dict[str, float]:
        """
        Kelly Criterion position sizing with Bayesian adjustment.
        
        Args:
            win_rate: Probability of winning (0-1)
            avg_win: Average win ratio (e.g., 1.5 for 1.5:1 reward)
            avg_loss: Average loss ratio (e.g., 1.0 for 1:1)
            fraction: Kelly fraction (0.5 = half-Kelly, recommended)
            min_kelly: Minimum Kelly fraction
            max_kelly: Maximum Kelly fraction (cap)
            
        Returns:
            Dict with full_kelly, half_kelly, recommended_kelly
        """
        if avg_loss == 0 or win_rate <= 0 or win_rate >= 1:
            return {"full_kelly": 0.0, "half_kelly": 0.0, "recommended_kelly": 0.0}

        # Full Kelly: f* = (p * b - q) / b
        # where p = win_rate, q = 1 - win_rate, b = avg_win / avg_loss
        b = avg_win / avg_loss
        full_kelly = (win_rate * b - (1 - win_rate)) / b

        # Apply fraction (half-Kelly is standard)
        adjusted_kelly = full_kelly * fraction

        # Cap between min and max
        recommended = max(min_kelly, min(adjusted_kelly, max_kelly))

        return {
            "full_kelly": round(max(0, full_kelly), 4),
            "half_kelly": round(max(0, full_kelly * 0.5), 4),
            "recommended_kelly": round(recommended, 4),
            "edge": round(win_rate * avg_win - (1 - win_rate) * avg_loss, 4),
        }

    def max_drawdown(self, equity_curve: np.ndarray) -> Dict[str, float]:
        """
        Maximum drawdown and duration analysis.
        
        Returns:
            Dict with max_drawdown, max_drawdown_duration_days, avg_drawdown
        """
        if len(equity_curve) < 2:
            return {"max_drawdown": 0.0, "max_drawdown_duration_days": 0, "avg_drawdown": 0.0}

        peak = np.maximum.accumulate(equity_curve)
        drawdown = (equity_curve - peak) / peak

        max_dd = float(np.min(drawdown))

        # Duration: longest consecutive period underwater
        underwater = drawdown < 0
        if not underwater.any():
            return {"max_drawdown": 0.0, "max_drawdown_duration_days": 0, "avg_drawdown": 0.0}

        # Count consecutive underwater days
        groups = np.cumsum(~underwater)
        durations = np.bincount(groups[underwater])
        max_duration = int(np.max(durations)) if len(durations) > 0 else 0
        avg_dd = float(np.mean(drawdown[underwater])) if underwater.any() else 0.0

        return {
            "max_drawdown": round(max_dd, 4),
            "max_drawdown_duration_days": max_duration,
            "avg_drawdown": round(avg_dd, 4),
        }

    def risk_reward_ratio(
        self,
        entry_price: float,
        target_price: float,
        stop_price: float,
    ) -> Dict[str, float]:
        """
        Calculate risk/reward ratio for a trade setup.
        
        Returns:
            Dict with ratio, reward_pct, risk_pct, breakeven_win_rate
        """
        risk = abs(entry_price - stop_price)
        reward = abs(target_price - entry_price)

        if risk == 0:
            return {"ratio": 0.0, "reward_pct": 0.0, "risk_pct": 0.0, "breakeven_win_rate": 1.0}

        ratio = reward / risk
        risk_pct = risk / entry_price
        reward_pct = reward / entry_price

        # Breakeven win rate: the minimum win rate needed for positive EV
        breakeven = 1 / (1 + ratio)

        return {
            "ratio": round(ratio, 2),
            "reward_pct": round(reward_pct * 100, 2),
            "risk_pct": round(risk_pct * 100, 2),
            "breakeven_win_rate": round(breakeven, 4),
        }

    def portfolio_correlation(self, returns: pd.DataFrame) -> Dict:
        """
        Analyze portfolio correlation structure.
        
        Returns:
            Dict with correlation matrix, average correlation, max correlation pair
        """
        if returns.empty or len(returns.columns) < 2:
            return {"avg_correlation": 0.0, "max_pair": None, "min_pair": None}

        corr_matrix = returns.corr()
        n = corr_matrix.shape[0]

        # Extract upper triangle (excluding diagonal)
        mask = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)
        upper_vals = corr_matrix.values[mask]

        if len(upper_vals) == 0:
            return {"avg_correlation": 0.0, "max_pair": None, "min_pair": None}

        avg_corr = float(np.mean(upper_vals))

        # Find max and min correlation pairs
        max_corr = -1
        min_corr = 1
        max_pair = None
        min_pair = None

        symbols = corr_matrix.columns.tolist()
        for i in range(n):
            for j in range(i + 1, n):
                c = corr_matrix.iloc[i, j]
                if c > max_corr:
                    max_corr = c
                    max_pair = (symbols[i], symbols[j], round(float(c), 4))
                if c < min_corr:
                    min_corr = c
                    min_pair = (symbols[i], symbols[j], round(float(c), 4))

        return {
            "avg_correlation": round(avg_corr, 4),
            "max_pair": max_pair,
            "min_pair": min_pair,
            "high_correlation_warning": avg_corr > 0.7,
        }

    def compute_all_risk_metrics(
        self,
        returns: np.ndarray,
        benchmark_returns: Optional[np.ndarray] = None,
        equity_curve: Optional[np.ndarray] = None,
    ) -> RiskMetrics:
        """
        Compute comprehensive risk metrics.
        
        Args:
            returns: Portfolio daily returns
            benchmark_returns: Benchmark daily returns (for beta/TE/IR)
            equity_curve: Portfolio equity curve (for drawdown analysis)
            
        Returns:
            RiskMetrics with all computed metrics
        """
        metrics = RiskMetrics()

        if len(returns) == 0:
            return metrics

        # VaR and CVaR
        metrics.var_95 = self.historical_var(returns, 0.95)
        metrics.var_99 = self.historical_var(returns, 0.99)
        metrics.cvar_95 = self.cvar(returns, 0.95)
        metrics.cvar_99 = self.cvar(returns, 0.99)

        # Volatility
        metrics.annualized_volatility = float(np.std(returns) * np.sqrt(252))

        # Downside volatility
        downside = returns[returns < 0]
        if len(downside) > 0:
            metrics.downside_volatility = float(np.std(downside) * np.sqrt(252))

        # Drawdown analysis
        if equity_curve is not None and len(equity_curve) > 0:
            dd_result = self.max_drawdown(equity_curve)
            metrics.max_drawdown = dd_result["max_drawdown"]
            metrics.max_drawdown_duration_days = dd_result["max_drawdown_duration_days"]

        # Beta and tracking error (if benchmark provided)
        if benchmark_returns is not None and len(benchmark_returns) == len(returns):
            # Beta
            cov = np.cov(returns, benchmark_returns)
            if cov[1, 1] > 0:
                metrics.beta = float(cov[0, 1] / cov[1, 1])

            # Tracking error
            active_returns = returns - benchmark_returns
            metrics.tracking_error = float(np.std(active_returns) * np.sqrt(252))

            # Information ratio
            if metrics.tracking_error > 0:
                metrics.information_ratio = float(np.mean(active_returns) / metrics.tracking_error)

        return metrics


# Singleton
risk_models = RiskModels()
