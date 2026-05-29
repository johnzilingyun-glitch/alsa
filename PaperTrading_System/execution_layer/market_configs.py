# execution_layer/market_configs.py

GLOBAL_BACKTEST_CONFIG = {
    "start_time": "2020-01-01",
    "end_time": "2021-12-31",
    "init_account": 10000000,
    "benchmark": "SH000300",
    "market_type": "CN",
    
    # 物理沙盒规则参数
    "exchange_kwargs": {
        "CN": {
            "limit_threshold": 0.099, # 涨跌停判定 (10%)
            "deal_price": "close",    # 撮合价位
            "open_cost": 0.00015,     # 建仓手续费
            "close_cost": 0.00115,    # 平仓手续费+印花税
            "min_cost": 5,            # 每笔最低佣金
            "trade_unit": 100         # 100股一手
        },
        "US": {
            "limit_threshold": None,  
            "deal_price": "close",
            "open_cost": 0.005,       
            "close_cost": 0.005,
            "min_cost": 1.0,          
            "trade_unit": 1           
        }
    }
}
