import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

class OKXDataFetcher:
    def __init__(self):
        self.api_key = os.getenv('OKX_API_KEY')
        self.secret = os.getenv('OKX_API_SECRET')
        self.passphrase = os.getenv('OKX_API_PASSPHRASE')
        
        self.exchange = ccxt.okx({
            'apiKey': self.api_key,
            'secret': self.secret,
            'password': self.passphrase,
            'sandbox': False,
            'enableRateLimit': True
        })
    
    def get_historical_data(self, symbol, timeframe='1h', days=30):
        """获取历史K线数据"""
        since = self.exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())
        
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('datetime', inplace=True)
            return df
        except Exception as e:
            print(f"获取数据失败: {e}")
            return None
    
    def get_market_data(self, symbols=None):
        """获取市场数据"""
        if symbols is None:
            symbols = ['BTC/USDT', 'ETH/USDT', 'AVAX/USDT', 'SOL/USDT', 'ADA/USDT']
        
        market_data = {}
        for symbol in symbols:
            try:
                ticker = self.exchange.fetch_ticker(symbol)
                market_data[symbol] = {
                    'symbol': symbol,
                    'price': ticker['last'],
                    'change': ticker['percentage'],
                    'high': ticker['high'],
                    'low': ticker['low'],
                    'volume': ticker['baseVolume']
                }
            except Exception as e:
                print(f"获取{symbol}数据失败: {e}")
        
        return market_data
    
    def get_available_symbols(self):
        """获取可交易品种"""
        markets = self.exchange.load_markets()
        usdt_symbols = [symbol for symbol in markets.keys() if symbol.endswith('/USDT')]
        return sorted(usdt_symbols)[:50]  # 返回前50个USDT交易对

if __name__ == "__main__":
    fetcher = OKXDataFetcher()
    
    # 测试数据获取
    print("获取BTC/USDT历史数据...")
    btc_data = fetcher.get_historical_data('BTC/USDT', '1h', 7)
    if btc_data is not None:
        print(f"获取到 {len(btc_data)} 条数据")
        print(btc_data.tail())
    
    print("\n获取市场数据...")
    market_data = fetcher.get_market_data()
    for symbol, data in market_data.items():
        print(f"{symbol}: ${data['price']} ({data['change']:.2f}%)")