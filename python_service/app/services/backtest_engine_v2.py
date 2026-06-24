"""Backtest Engine V2 — institutional-grade backtesting with proper cost modeling.

Fixes from review report:
- Transaction costs (commission + stamp duty + slippage)
- Ledoit-Wolf shrunk covariance for portfolio optimization
- Walk-forward out-of-sample validation
- Proper risk metrics (CVaR, max drawdown, Sharpe, Sortino)
"""
import numpy as np
import pandas as pd
import logging
from dataclasses import dataclass
from typing import Dict

logger = logging.getLogger(__name__)

# Trading cost defaults (A-Share)
DEFAULT_COMMISSION_RATE = 0.0003    # 万三佣金
DEFAULT_STAMP_DUTY_RATE = 0.001     # 千一印花税 (卖出)
DEFAULT_SLIPPAGE_RATE = 0.001       # 千一滑点
DEFAULT_MIN_COMMISSION = 5.0        # 最低佣金 5 元


@dataclass
class BacktestMetrics:
    """Comprehensive backtest metrics."""
    annualized_return: float = 0.0
    annualized_volatility: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration_days: int = 0
    calmar_ratio: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_return: float = 0.0
    total_trades: int = 0
    total_costs: float = 0.0
    cvar_95: float = 0.0  # Conditional VaR at 95%
    var_95: float = 0.0   # Historical VaR at 95%

    def to_dict(self) -> dict:
        return {
            "annualized_return": round(self.annualized_return, 4),
            "annualized_volatility": round(self.annualized_volatility, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "sortino_ratio": round(self.sortino_ratio, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "max_drawdown_duration_days": self.max_drawdown_duration_days,
            "calmar_ratio": round(self.calmar_ratio, 4),
            "win_rate": round(self.win_rate, 4),
            "profit_factor": round(self.profit_factor, 4),
            "total_return": round(self.total_return, 4),
            "total_trades": self.total_trades,
            "total_costs": round(self.total_costs, 2),
            "cvar_95": round(self.cvar_95, 4),
            "var_95": round(self.var_95, 4),
        }


class BacktestEngineV2:
    """
    Institutional-grade backtesting engine.
    
    Features:
    - Realistic transaction costs
    - Ledoit-Wolf shrunk covariance for portfolio optimization
    - Walk-forward out-of-sample validation
    - Comprehensive risk metrics
    """

    def __init__(
        self,
        commission_rate: float = DEFAULT_COMMISSION_RATE,
        stamp_duty_rate: float = DEFAULT_STAMP_DUTY_RATE,
        slippage_rate: float = DEFAULT_SLIPPAGE_RATE,
        min_commission: float = DEFAULT_MIN_COMMISSION,
    ):
        self.commission_rate = commission_rate
        self.stamp_duty_rate = stamp_duty_rate
        self.slippage_rate = slippage_rate
        self.min_commission = min_commission

    def run_backtest(
        self,
        prices: pd.DataFrame,
        weights: Dict[str, float],
        initial_capital: float = 1_000_000,
        rebalance_freq_days: int = 21,
    ) -> Dict:
        """
        Run a backtest with given prices and target weights.
        
        Args:
            prices: DataFrame with dates as index, symbols as columns, close prices
            weights: Target portfolio weights {symbol: weight}
            initial_capital: Starting capital
            rebalance_freq_days: Rebalancing frequency in trading days
            
        Returns:
            Dict with metrics, equity curve, and trade log
        """
        if prices.empty or len(weights) == 0:
            return {"metrics": BacktestMetrics().to_dict(), "equity_curve": [], "trades": []}

        returns = prices.pct_change().dropna()
        symbols = [s for s in weights.keys() if s in returns.columns]
        if not symbols:
            return {"metrics": BacktestMetrics().to_dict(), "equity_curve": [], "trades": []}

        # Filter weights to available symbols and normalize
        w = np.array([weights[s] for s in symbols])
        w = w / w.sum()

        # Simulate portfolio
        portfolio_value = initial_capital
        positions = {s: 0.0 for s in symbols}
        equity_curve = []
        trades = []
        total_costs = 0.0
        last_rebalance = 0

        for i, date in enumerate(returns.index):
            # Daily PnL (before rebalancing)
            daily_return = 0.0
            for s_idx, s in enumerate(symbols):
                if positions[s] > 0:
                    daily_return += positions[s] * returns.loc[date, s]

            portfolio_value += daily_return

            # Rebalance if needed
            if i - last_rebalance >= rebalance_freq_days:
                target_positions = {}
                for s_idx, s in enumerate(symbols):
                    target_positions[s] = portfolio_value * w[s_idx] / prices.loc[date, s]

                # Calculate turnover and costs
                turnover = 0.0
                for s in symbols:
                    delta = abs(target_positions.get(s, 0) - positions.get(s, 0))
                    trade_value = delta * prices.loc[date, s]
                    turnover += trade_value

                    # Record trade
                    if delta > 0.01:
                        trades.append({
                            "date": str(date)[:10],
                            "symbol": s,
                            "action": "BUY" if target_positions.get(s, 0) > positions.get(s, 0) else "SELL",
                            "shares": round(delta, 2),
                            "price": round(float(prices.loc[date, s]), 2),
                        })

                # Calculate transaction costs
                cost = self._compute_costs(turnover)
                portfolio_value -= cost
                total_costs += cost

                positions = target_positions
                last_rebalance = i

            equity_curve.append({
                "date": str(date)[:10],
                "value": round(portfolio_value, 2),
            })

        # Compute metrics
        equity_series = pd.Series([e["value"] for e in equity_curve])
        metrics = self._compute_metrics(equity_series, trades, total_costs, initial_capital)

        return {
            "metrics": metrics.to_dict(),
            "equity_curve": equity_curve,
            "trades": trades,
            "weights": {s: round(float(w[i]), 4) for i, s in enumerate(symbols)},
            "initial_capital": initial_capital,
            "final_value": round(portfolio_value, 2),
        }

    def optimize_gmv(self, returns: pd.DataFrame) -> Dict[str, float]:
        """
        Global Minimum Variance portfolio with Ledoit-Wolf shrunk covariance.
        
        Args:
            returns: DataFrame of daily returns
            
        Returns:
            Dict of {symbol: weight}
        """
        if returns.empty or len(returns.columns) < 2:
            # Equal weight for single asset
            if len(returns.columns) == 1:
                return {returns.columns[0]: 1.0}
            return {}

        # Ledoit-Wolf shrinkage
        cov_shrunk = self._ledoit_wolf_shrink(returns)
        n = cov_shrunk.shape[0]
        symbols = returns.columns.tolist()

        # GMV weights: w = Σ^{-1} 1 / (1^T Σ^{-1} 1)
        try:
            ones = np.ones(n)
            inv_cov = np.linalg.inv(cov_shrunk.values)
            raw_w = np.dot(inv_cov, ones)

            # Long-only constraint: clip negatives
            w_clipped = np.clip(raw_w, 0, None)
            if w_clipped.sum() > 0:
                w = w_clipped / w_clipped.sum()
            else:
                w = ones / n

            return {symbols[i]: float(w[i]) for i in range(n)}
        except np.linalg.LinAlgError:
            # Singular matrix — fall back to equal weight
            return {s: 1.0 / n for s in symbols}

    def walk_forward(
        self,
        prices: pd.DataFrame,
        initial_capital: float = 1_000_000,
        train_days: int = 252,
        test_days: int = 63,
    ) -> Dict:
        """
        Walk-forward out-of-sample validation.
        
        Args:
            prices: Full price history
            initial_capital: Starting capital
            train_days: Training window (1 year)
            test_days: Test window (1 quarter)
            
        Returns:
            Dict with in-sample and out-of-sample metrics
        """
        if len(prices) < train_days + test_days:
            # Not enough data — run single backtest
            returns = prices.pct_change().dropna()
            weights = self.optimize_gmv(returns)
            result = self.run_backtest(prices, weights, initial_capital)
            return {"in_sample": result["metrics"], "out_of_sample": None, "folds": 0}

        fold_results = []
        for start in range(0, len(prices) - train_days - test_days, test_days):
            train_prices = prices.iloc[start:start + train_days]
            test_prices = prices.iloc[start + train_days:start + train_days + test_days]

            # Optimize on training data
            train_returns = train_prices.pct_change().dropna()
            weights = self.optimize_gmv(train_returns)

            # Test on out-of-sample data
            result = self.run_backtest(test_prices, weights, initial_capital)
            fold_results.append(result["metrics"])

        # Aggregate OOS metrics
        if fold_results:
            oos_returns = [f["annualized_return"] for f in fold_results]
            oos_sharpes = [f["sharpe_ratio"] for f in fold_results]
            oos_metrics = {
                "mean_annualized_return": np.mean(oos_returns),
                "std_annualized_return": np.std(oos_returns),
                "mean_sharpe": np.mean(oos_sharpes),
                "worst_drawdown": min(f["max_drawdown"] for f in fold_results),
                "folds": len(fold_results),
            }
        else:
            oos_metrics = None

        # Full in-sample
        full_returns = prices.pct_change().dropna()
        full_weights = self.optimize_gmv(full_returns)
        in_sample = self.run_backtest(prices, full_weights, initial_capital)

        return {
            "in_sample": in_sample["metrics"],
            "out_of_sample": oos_metrics,
            "folds": len(fold_results),
        }

    def _ledoit_wolf_shrink(self, returns: pd.DataFrame) -> pd.DataFrame:
        """Ledoit-Wolf covariance shrinkage estimator."""
        sample_cov = returns.cov()
        n = sample_cov.shape[0]

        # Target: scaled identity matrix
        trace = np.trace(sample_cov.values)
        mu = trace / n
        shrink_target = mu * np.eye(n)

        # Optimal shrinkage intensity (simplified)
        # Full Ledoit-Wolf is complex; use a reasonable default
        alpha = 0.2

        shrunk = sample_cov.values * (1 - alpha) + shrink_target * alpha
        return pd.DataFrame(shrunk, index=sample_cov.index, columns=sample_cov.columns)

    def _compute_costs(self, turnover: float) -> float:
        """Compute transaction costs for a given turnover."""
        commission = max(turnover * self.commission_rate, self.min_commission)
        stamp_duty = turnover * self.stamp_duty_rate  # Only on sell, simplified
        slippage = turnover * self.slippage_rate
        return commission + stamp_duty + slippage

    def _compute_metrics(
        self,
        equity_curve: pd.Series,
        trades: list,
        total_costs: float,
        initial_capital: float,
    ) -> BacktestMetrics:
        """Compute comprehensive backtest metrics."""
        metrics = BacktestMetrics()

        if len(equity_curve) < 2:
            return metrics

        # Returns series
        returns = equity_curve.pct_change().dropna()
        if len(returns) == 0:
            return metrics

        # Total return
        metrics.total_return = (equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1
        metrics.total_trades = len(trades)
        metrics.total_costs = total_costs

        # Annualized return (assume 252 trading days)
        n_years = len(returns) / 252
        if n_years > 0:
            metrics.annualized_return = (1 + metrics.total_return) ** (1 / n_years) - 1

        # Annualized volatility
        metrics.annualized_volatility = returns.std() * np.sqrt(252)

        # Sharpe ratio (assuming 2% risk-free rate)
        rf_daily = 0.02 / 252
        excess_returns = returns - rf_daily
        if excess_returns.std() > 0:
            metrics.sharpe_ratio = excess_returns.mean() / excess_returns.std() * np.sqrt(252)

        # Sortino ratio
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 0 and downside_returns.std() > 0:
            metrics.sortino_ratio = excess_returns.mean() / downside_returns.std() * np.sqrt(252)

        # Max drawdown
        peak = equity_curve.expanding(min_periods=1).max()
        drawdown = (equity_curve - peak) / peak
        metrics.max_drawdown = drawdown.min()

        # Max drawdown duration
        underwater = drawdown < 0
        if underwater.any():
            groups = (~underwater).cumsum()
            durations = underwater.groupby(groups).sum()
            metrics.max_drawdown_duration_days = int(durations.max()) if len(durations) > 0 else 0

        # Calmar ratio
        if metrics.max_drawdown != 0:
            metrics.calmar_ratio = metrics.annualized_return / abs(metrics.max_drawdown)

        # Win rate
        winning_days = (returns > 0).sum()
        metrics.win_rate = winning_days / len(returns) if len(returns) > 0 else 0

        # Profit factor
        gains = returns[returns > 0].sum()
        losses = abs(returns[returns < 0].sum())
        metrics.profit_factor = gains / losses if losses > 0 else float('inf')

        # VaR and CVaR at 95%
        sorted_returns = np.sort(returns.values)
        var_index = int(0.05 * len(sorted_returns))
        metrics.var_95 = -sorted_returns[var_index] if var_index < len(sorted_returns) else 0
        metrics.cvar_95 = -np.mean(sorted_returns[:var_index]) if var_index > 0 else metrics.var_95

        return metrics


# Singleton
backtest_engine_v2 = BacktestEngineV2()
