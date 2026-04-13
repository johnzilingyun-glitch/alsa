import sys
import json
import yfinance as yf
import pandas as pd
from datetime import datetime

def get_stock_data(symbol, market):
    """
    获取实时股票数据
    """
    try:
        # 针对不同市场调整代码后缀
        yf_symbol = symbol
        if market == "A-Share":
            if symbol.startswith('6'):
                yf_symbol = f"{symbol}.SS"
            else:
                yf_symbol = f"{symbol}.SZ"
        elif market == "HK-Share":
            # 港股通常是 5 位数字，yfinance 需要 .HK
            yf_symbol = f"{symbol.zfill(5)}.HK"
            
        ticker = yf.Ticker(yf_symbol)
        info = ticker.info
        
        # 获取最新价格数据
        # yfinance 的 info 包含很多字段，我们提取核心字段
        data = {
            "symbol": symbol,
            "name": info.get("shortName", symbol),
            "price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "previousClose": info.get("regularMarketPreviousClose"),
            "open": info.get("open"),
            "dayHigh": info.get("dayHigh"),
            "dayLow": info.get("dayLow"),
            "volume": info.get("volume"),
            "marketCap": info.get("marketCap"),
            "pe": info.get("trailingPE"),
            "forwardPE": info.get("forwardPE"),
            "dividendYield": info.get("dividendYield"),
            "currency": info.get("currency", "CNY"),
            "lastUpdated": datetime.now().strftime("%Y-%m-%d %H:%M:%S CST"),
            "source": "Yahoo Finance API via Python Tool"
        }
        
        # 计算涨跌幅
        if data["price"] and data["previousClose"]:
            data["change"] = round(data["price"] - data["previousClose"], 4)
            data["changePercent"] = round((data["change"] / data["previousClose"]) * 100, 2)
        else:
            data["change"] = 0
            data["changePercent"] = 0
            
        return data
    except Exception as e:
        return {"error": str(e), "symbol": symbol}

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Missing arguments"}))
        sys.exit(1)
        
    symbol = sys.argv[1]
    market = sys.argv[2]
    
    result = get_stock_data(symbol, market)
    print(json.dumps(result, ensure_ascii=False))
