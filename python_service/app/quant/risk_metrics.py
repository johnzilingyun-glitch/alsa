import pandas as pd
import numpy as np
from scipy import stats
import logging

logger = logging.getLogger(__name__)

class RiskMetrics:
    @staticmethod
    def compute_var(returns: pd.Series, confidence: float = 0.95) -> float:
        """
        Compute Parametric Value at Risk (VaR).
        """
        if returns.empty:
            return 0.0
        mu = returns.mean()
        sigma = returns.std()
        # stats.norm.ppf returns the percentile point function
        return stats.norm.ppf(1 - confidence, mu, sigma)

    @staticmethod
    def compute_sharpe(returns: pd.Series, rf: float = 0.03, periods_per_year: int = 252) -> float:
        """
        Compute Annualized Sharpe Ratio.
        rf: Annualized risk-free rate
        """
        if returns.empty or returns.std() == 0:
            return 0.0
        
        # Adjust rf to match the period of the returns
        daily_rf = rf / periods_per_year
        excess_returns = returns - daily_rf
        
        return (excess_returns.mean() / excess_returns.std()) * np.sqrt(periods_per_year)

    @staticmethod
    def compute_max_drawdown(equity_curve: pd.Series) -> float:
        """
        Compute Maximum Drawdown from an equity curve (prices or cumulative returns).
        """
        if equity_curve.empty:
            return 0.0
        
        peak = equity_curve.expanding(min_periods=1).max()
        drawdown = (equity_curve - peak) / peak
        return drawdown.min()
