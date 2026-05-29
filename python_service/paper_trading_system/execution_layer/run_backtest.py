import qlib
from qlib.constant import REG_CN
from qlib.utils import exists_qlib_data
from qlib.backtest import backtest, executor
from qlib.backtest.account import Account
from qlib.contrib.evaluate import risk_analysis
import pandas as pd
import logging
import os

from paper_trading_system.decision_layer.agent_models import MockAgent
from paper_trading_system.decision_layer.strategy_bridge import AIAgentStrategy
from paper_trading_system.execution_layer.market_configs import get_exchange_kwargs

logger = logging.getLogger(__name__)

def run_historical_backtest(
    provider_uri: str = "~/.qlib/qlib_data/cn_data",
    market: str = "CN",
    start_time: str = "2023-01-01",
    end_time: str = "2023-12-31",
    initial_cash: float = 1000000.0,
):
    """
    Run a full historical backtest using SimulatorExecutor and AIAgentStrategy.
    """
    # 1. Initialize Qlib with specific data provider
    qlib.init(provider_uri=provider_uri, region=REG_CN)
    
    if not exists_qlib_data(provider_uri):
        logger.warning(f"Qlib data not found at {provider_uri}. Please download data first.")
        # For demonstration, we'll continue, but qlib will throw errors when fetching data.

    # 2. Setup AI Agent and Strategy Bridge
    agent = MockAgent(market_type=market)
    strategy = AIAgentStrategy(agent_model=agent, market_type=market)
    
    # 3. Setup Executor with Market-Specific Rules
    exchange_kwargs = get_exchange_kwargs(market)
    trade_executor = executor.SimulatorExecutor(
        time_per_step="day",
        generate_portfolio_metrics=True,
        verbose=True,
        **exchange_kwargs
    )
    
    # 4. Setup Initial Account
    account = Account(init_cash=initial_cash)
    
    # 5. Run Backtest Loop
    portfolio_metric_dict, indicator_dict = backtest(
        start_time=pd.Timestamp(start_time),
        end_time=pd.Timestamp(end_time),
        strategy=strategy,
        executor=trade_executor,
        account=account,
    )
    
    # 6. Evaluate and Export Reports
    analysis_df = risk_analysis(portfolio_metric_dict["1day"][0])
    print("=== Backtest Risk Analysis ===")
    print(analysis_df)
    
    # Save reports
    os.makedirs("output/reports", exist_ok=True)
    report_path = f"output/reports/backtest_{market}_{start_time}_{end_time}.csv"
    portfolio_metric_dict["1day"][0].to_csv(report_path)
    print(f"Report saved to {report_path}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_historical_backtest()
