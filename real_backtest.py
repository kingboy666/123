import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import talib
from data_fetcher import OKXDataFetcher
import json

class RealBacktestEngine:
    def __init__(self):
        self.fetcher = OKXDataFetcher()
        self.results = {}
    
    def calculate_indicators(self, df):
        """计算技术指标"""
        # MACD
        df['macd'], df['macd_signal'], df['macd_hist'] = talib.MACD(df['close'])
        
        # RSI
        df['rsi'] = talib.RSI(df['close'])
        
        # 布林带
        df['bb_upper'], df['bb_middle'], df['bb_lower'] = talib.BBANDS(df['close'])
        
        # KDJ
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        
        # 使用talib计算KDJ (需要将数据转换为numpy数组)
        df['k'], df['d'] = talib.STOCH(high, low, close)
        df['j'] = 3 * df['k'] - 2 * df['d']
        
        # EMA
        df['ema_10'] = talib.EMA(df['close'], timeperiod=10)
        df['ema_20'] = talib.EMA(df['close'], timeperiod=20)
        
        # ADX
        df['adx'] = talib.ADX(high, low, close)
        
        # ATR
        df['atr'] = talib.ATR(high, low, close)
        
        return df
    
    def strategy_macd_rsi_bollinger(self, df):
        """策略1: MACD + RSI + 布林带"""
        signals = []
        position = 0  # 0: 无仓位, 1: 多头, -1: 空头
        
        for i in range(1, len(df)):
            # 做多信号
            if (df['macd'].iloc[i] > df['macd_signal'].iloc[i] and 
                df['rsi'].iloc[i] > 30 and df['rsi'].iloc[i] < 70 and
                df['close'].iloc[i] > df['bb_lower'].iloc[i] and position != 1):
                signals.append(1)
                position = 1
            # 做空信号
            elif (df['macd'].iloc[i] < df['macd_signal'].iloc[i] and 
                  df['rsi'].iloc[i] < 70 and df['rsi'].iloc[i] > 30 and
                  df['close'].iloc[i] < df['bb_upper'].iloc[i] and position != -1):
                signals.append(-1)
                position = -1
            else:
                signals.append(0)
        
        return signals
    
    def strategy_kdj_ma_volume(self, df):
        """策略2: KDJ + MA + 成交量"""
        signals = []
        position = 0
        
        for i in range(1, len(df)):
            # 简化策略逻辑
            k_above_d = df['k'].iloc[i] > df['d'].iloc[i]
            price_above_ema = df['close'].iloc[i] > df['ema_10'].iloc[i]
            volume_ok = df['volume'].iloc[i] > df['volume'].rolling(5).mean().iloc[i]
            
            if k_above_d and price_above_ema and volume_ok and position != 1:
                signals.append(1)
                position = 1
            elif not k_above_d and not price_above_ema and position != -1:
                signals.append(-1)
                position = -1
            else:
                signals.append(0)
        
        return signals
    
    def strategy_adx_ema_rsi(self, df):
        """策略3: ADX + EMA + RSI"""
        signals = []
        position = 0
        
        for i in range(1, len(df)):
            strong_trend = df['adx'].iloc[i] > 25
            ema_bullish = df['ema_10'].iloc[i] > df['ema_20'].iloc[i]
            rsi_ok = 30 < df['rsi'].iloc[i] < 70
            
            if strong_trend and ema_bullish and rsi_ok and position != 1:
                signals.append(1)
                position = 1
            elif strong_trend and not ema_bullish and rsi_ok and position != -1:
                signals.append(-1)
                position = -1
            else:
                signals.append(0)
        
        return signals
    
    def run_backtest(self, symbol, strategy_func, days=30, timeframe='1h'):
        """运行回测"""
        print(f"正在获取 {symbol} 的历史数据...")
        df = self.fetcher.get_historical_data(symbol, timeframe, days)
        
        if df is None or len(df) == 0:
            return {"error": f"无法获取{symbol}数据"}
        
        print(f"获取到 {len(df)} 条数据，计算技术指标...")
        df = self.calculate_indicators(df)
        
        print("执行策略...")
        signals = strategy_func(df)
        df = df.iloc[1:]  # 移除第一行（没有信号）
        df['signal'] = signals
        
        # 计算收益
        df['returns'] = df['close'].pct_change()
        df['strategy_returns'] = df['signal'].shift(1) * df['returns']
        
        # 统计结果
        total_return = df['strategy_returns'].sum()
        win_rate = (df['strategy_returns'] > 0).mean()
        total_trades = (df['signal'].abs().diff() != 0).sum()
        
        return {
            'symbol': symbol,
            'total_return': total_return,
            'win_rate': win_rate,
            'total_trades': total_trades,
            'data_points': len(df),
            'sharpe_ratio': df['strategy_returns'].mean() / df['strategy_returns'].std() if df['strategy_returns'].std() != 0 else 0
        }
    
    def run_all_strategies(self, symbols=None):
        """运行所有策略"""
        if symbols is None:
            symbols = ['BTC/USDT', 'ETH/USDT', 'AVAX/USDT']
        
        strategies = {
            'MACD+RSI+布林带': self.strategy_macd_rsi_bollinger,
            'KDJ+MA+成交量': self.strategy_kdj_ma_volume,
            'ADX+EMA+RSI': self.strategy_adx_ema_rsi
        }
        
        results = {}
        
        for strategy_name, strategy_func in strategies.items():
            print(f"\n=== 测试策略: {strategy_name} ===")
            strategy_results = []
            
            for symbol in symbols:
                result = self.run_backtest(symbol, strategy_func)
                if 'error' not in result:
                    strategy_results.append(result)
                    print(f"{symbol}: 总收益 {result['total_return']:.2%}, 胜率 {result['win_rate']:.2%}")
            
            results[strategy_name] = strategy_results
        
        return results

if __name__ == "__main__":
    engine = RealBacktestEngine()
    
    print("开始真实数据回测...")
    results = engine.run_all_strategies()
    
    print("\n=== 回测结果汇总 ===")
    for strategy, strategy_results in results.items():
        print(f"\n策略: {strategy}")
        for result in strategy_results:
            print(f"  {result['symbol']}: 收益{result['total_return']:.2%}, 胜率{result['win_rate']:.2%}, 交易次数{result['total_trades']}")