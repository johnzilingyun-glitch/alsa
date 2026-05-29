"""
Market specific configuration dictionaries for Qlib SimulatorExecutor.
These kwargs map to Qlib's executor configuration.
"""

# A股虚拟沙盒配置
CN_EXCHANGE_KWARGS = {
    "limit_threshold": 0.099, # 10% 涨跌停
    "deal_price": "close",    # 撮合价，使用每日收盘价
    "open_cost": 0.00015,     # 开仓滑点+佣金
    "close_cost": 0.00115,    # 平仓含印花税
    "min_cost": 5,            # 最低消费
    "trade_unit": 100,        # A股一手 100 股
}

# 美股虚拟沙盒配置
US_EXCHANGE_KWARGS = {
    "limit_threshold": None,  # 无涨跌停
    "deal_price": "close",
    "open_cost": 0.005,       # 假设每股 $0.005 佣金
    "close_cost": 0.005,
    "min_cost": 1,            # 假设最低消费 $1
    "trade_unit": 1,          # 美股 1 股起
}

# 港股虚拟沙盒配置
HK_EXCHANGE_KWARGS = {
    "limit_threshold": None,  # 无涨跌停限制
    "deal_price": "close",
    "open_cost": 0.001,       # 印花税及滑点等综合预估
    "close_cost": 0.002,      # 卖出成本略高
    "min_cost": 15,           # 港币最低消费较高
    # 注意: 港股实际每只股票 lot size 不同 (如100, 400, 500等)
    # 在 SimulatorExecutor 层如果不做定制，只能用一个默认值，或者在 Strategy 里生成 Order 时处理。
    # 这里我们设置默认值为1，但在 AIAgentStrategy._calculate_delta_and_format_orders 会有严格处理。
    "trade_unit": 1,          
}

def get_exchange_kwargs(market: str) -> dict:
    """Helper to return the kwargs for Qlib's Exchange class."""
    if market in ("CN", "A-Share"):
        return CN_EXCHANGE_KWARGS
    elif market in ("US", "US-Share"):
        return US_EXCHANGE_KWARGS
    elif market in ("HK", "HK-Share"):
        return HK_EXCHANGE_KWARGS
    else:
        raise ValueError(f"Unknown market: {market}")
