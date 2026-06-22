"""
Monte Carlo回测验证：通过随机扰动评估策略稳健性
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, Callable, Optional
from datetime import datetime


class MonteCarloBacktester:
    """蒙特卡洛回测引擎"""
    
    def __init__(self, n_simulations: int = 1000, random_seed: Optional[int] = None):
        self.n_simulations = n_simulations
        if random_seed is not None:
            np.random.seed(random_seed)
    
    async def run_backtest(
        self,
        price_data: pd.DataFrame,
        strategy_func: Callable,
        slippage_range: float = 0.05,  # ±5%价格滑点
        timing_range: int = 1,          # ±1天时间偏移
        confidence_level: float = 0.95
    ) -> Dict[str, Any]:
        """
        运行蒙特卡洛回测
        
        Args:
            price_data: 历史价格数据（需包含Close列）
            strategy_func: 策略函数，输入DataFrame，输出{'total_return': float, 'sharpe': float}
            slippage_range: 价格扰动范围（百分比）
            timing_range: 时间偏移范围（天数）
            confidence_level: 置信水平
            
        Returns:
            回测结果，包含VaR、Sharpe分布、盈利概率等
        """
        results = []
        
        for _ in range(self.n_simulations):
            # 生成扰动数据
            perturbed_data = self._add_noise(
                price_data.copy(), 
                slippage_range, 
                timing_range
            )
            
            try:
                result = strategy_func(perturbed_data)
                results.append(result)
            except Exception:
                # 策略执行失败，跳过
                continue
        
        if not results:
            return {
                "error": "All simulations failed",
                "n_successful": 0,
                "n_total": self.n_simulations
            }
        
        # 提取指标
        returns = [r.get('total_return', 0) for r in results]
        sharpes = [r.get('sharpe', 0) for r in results]
        max_dds = [r.get('max_drawdown', 0) for r in results]
        
        # 计算VaR
        var_percentile = (1 - confidence_level) * 100
        var = np.percentile(returns, var_percentile)
        cvar = np.mean([r for r in returns if r <= var]) if any(r <= var for r in returns) else var
        
        return {
            "n_simulations": self.n_simulations,
            "n_successful": len(results),
            "confidence_level": confidence_level,
            
            # 收益分布
            "return_stats": {
                "mean": float(np.mean(returns)),
                "std": float(np.std(returns)),
                "min": float(np.min(returns)),
                "max": float(np.max(returns)),
                "median": float(np.median(returns)),
                "percentile_5": float(np.percentile(returns, 5)),
                "percentile_95": float(np.percentile(returns, 95))
            },
            
            # 风险指标
            "risk_metrics": {
                f"var_{int(confidence_level*100)}": float(var),
                f"cvar_{int(confidence_level*100)}": float(cvar),
                "max_drawdown_mean": float(np.mean(max_dds)),
                "max_drawdown_std": float(np.std(max_dds))
            },
            
            # Sharpe分布
            "sharpe_stats": {
                "mean": float(np.mean(sharpes)),
                "std": float(np.std(sharpes)),
                "min": float(np.min(sharpes)),
                "max": float(np.max(sharpes))
            },
            
            # 概率统计
            "probabilities": {
                "probability_of_profit": float(sum(1 for r in returns if r > 0) / len(returns)),
                "probability_of_loss_gt_10pct": float(sum(1 for r in returns if r < -0.1) / len(returns)),
                "probability_of_sharpe_gt_1": float(sum(1 for s in sharpes if s > 1) / len(sharpes))
            },
            
            "timestamp": datetime.now().isoformat()
        }
    
    def _add_noise(
        self, 
        data: pd.DataFrame, 
        slippage_range: float, 
        timing_range: int
    ) -> pd.DataFrame:
        """添加随机扰动"""
        df = data.copy()
        
        # 价格扰动：±slippage_range
        if 'Close' in df.columns:
            noise = np.random.uniform(1 - slippage_range, 1 + slippage_range, len(df))
            df['Close'] = df['Close'] * noise
        
        # 时间扰动：随机偏移±timing_range天
        if timing_range > 0 and len(df) > timing_range * 2:
            shift = np.random.randint(-timing_range, timing_range + 1)
            df = df.shift(shift).dropna()
        
        return df
    
    def generate_report(self, results: Dict[str, Any]) -> str:
        """生成可读的回测报告"""
        if "error" in results:
            return f"回测失败: {results['error']}"
        
        ret = results["return_stats"]
        risk = results["risk_metrics"]
        prob = results["probabilities"]
        
        report = f"""# 蒙特卡洛回测报告

## 基本信息
- 模拟次数: {results['n_simulations']}
- 成功次数: {results['n_successful']}
- 置信水平: {results['confidence_level']*100:.0f}%

## 收益分布
- 平均收益: {ret['mean']*100:.2f}%
- 收益标准差: {ret['std']*100:.2f}%
- 最大收益: {ret['max']*100:.2f}%
- 最小收益: {ret['min']*100:.2f}%
- 中位数收益: {ret['median']*100:.2f}%

## 风险指标
- VaR({int(results['confidence_level']*100)}%): {risk[f"var_{int(results['confidence_level']*100)}"]*100:.2f}%
- CVaR({int(results['confidence_level']*100)}%): {risk[f"cvar_{int(results['confidence_level']*100)}"]*100:.2f}%
- 平均最大回撤: {risk['max_drawdown_mean']*100:.2f}%

## Sharpe比率分布
- 平均Sharpe: {results['sharpe_stats']['mean']:.2f}
- Sharpe标准差: {results['sharpe_stats']['std']:.2f}

## 概率统计
- 盈利概率: {prob['probability_of_profit']*100:.1f}%
- 亏损>10%概率: {prob['probability_of_loss_gt_10pct']*100:.1f}%
- Sharpe>1概率: {prob['probability_of_sharpe_gt_1']*100:.1f}%
"""
        return report


# 单例
monte_carlo_backtester = MonteCarloBacktester()
