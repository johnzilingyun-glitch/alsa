import pandas as pd
import numpy as np
import logging
from ..config import RISK_FREE_RATE

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
        if sigma == 0:
            return mu
            
        from statistics import NormalDist
        dist = NormalDist(mu, sigma)
        return dist.inv_cdf(1 - confidence)

    @staticmethod
    def compute_sharpe(returns: pd.Series, rf: float = RISK_FREE_RATE, periods_per_year: int = 252) -> float:
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

    @staticmethod
    def compute_sortino(returns: pd.Series, rf: float = RISK_FREE_RATE, periods_per_year: int = 252) -> float:
        """
        Compute Annualized Sortino Ratio.
        rf: Annualized risk-free rate
        """
        if returns.empty:
            return 0.0
            
        daily_rf = rf / periods_per_year
        excess_returns = returns - daily_rf
        
        # We only consider returns that are below the daily target return (MAR = daily_rf)
        downside_returns = excess_returns[excess_returns < 0]
        if downside_returns.empty:
            return 0.0
            
        # Calculate downside deviation: standard deviation of negative excess returns
        downside_std = np.sqrt(np.mean(downside_returns ** 2))
        if downside_std == 0:
            return 0.0
            
        return (excess_returns.mean() / downside_std) * np.sqrt(periods_per_year)

    @staticmethod
    def compute_altman_z_score(working_capital: float, retained_earnings: float, ebit: float, market_cap: float, total_assets: float, total_liabilities: float) -> float:
        """
        Compute Altman Z-Score for predicting bankruptcy risk.
        Z = 1.2A + 1.4B + 3.3C + 0.6D + 1.0E
        Where:
        A = Working Capital / Total Assets
        B = Retained Earnings / Total Assets
        C = EBIT / Total Assets
        D = Market Value of Equity / Total Liabilities
        E = Sales / Total Assets (Using 1.0 proxy if Sales not available, though technically required. Here we omit Sales term E for a modified Z'-score or assume provided if possible)
        We will implement the standard Z-score (assuming Sales = Total Assets as a rough fallback if not provided, but ideally we need sales. 
        For simplicity in this signature, we compute the 4-variable Z'' score for non-manufacturers: Z'' = 6.56A + 3.26B + 6.72C + 1.05D)
        """
        if total_assets <= 0 or total_liabilities <= 0:
            return 0.0
            
        A = working_capital / total_assets
        B = retained_earnings / total_assets
        C = ebit / total_assets
        D = market_cap / total_liabilities
        
        # Using the Z'' score for emerging markets / non-manufacturing
        z_score = 6.56 * A + 3.26 * B + 6.72 * C + 1.05 * D
        return z_score

    @staticmethod
    def compute_piotroski_f_score(net_income: float, operating_cash_flow: float, roa_current: float, roa_prev: float, cfo_gt_ni: bool, 
                                 lt_debt_current: float, lt_debt_prev: float, current_ratio_current: float, current_ratio_prev: float,
                                 shares_current: float, shares_prev: float, gross_margin_current: float, gross_margin_prev: float,
                                 asset_turnover_current: float, asset_turnover_prev: float) -> int:
        """
        Compute Piotroski F-Score (0-9) to assess strength of value stocks.
        """
        score = 0
        # Profitability
        if net_income > 0: score += 1
        if operating_cash_flow > 0: score += 1
        if roa_current > roa_prev: score += 1
        if cfo_gt_ni: score += 1  # CFO > Net Income
        
        # Leverage, Liquidity and Source of Funds
        if lt_debt_current < lt_debt_prev: score += 1
        if current_ratio_current > current_ratio_prev: score += 1
        if shares_current <= shares_prev: score += 1  # No dilution
        
        # Operating Efficiency
        if gross_margin_current > gross_margin_prev: score += 1
        if asset_turnover_current > asset_turnover_prev: score += 1
        
        return score

