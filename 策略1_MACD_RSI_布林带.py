"""
策略1: MACD + RSI + 布林带组合
特点：趋势跟踪 + 超买超卖 + 波动率判断
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import talib

class MACD_RSI_BollingerStrategy:
    def __init__(self):
        self.name = "MACD+RSI+布林带策略"
        self.description = "趋势跟踪与超买超卖结合"
        
    def calculate_signals(self, df):
        """计算交易信号"""
        # MACD指标
        macd, macd_signal, macd_hist = talib.MACD(df['close'], fastperiod=12, slowperiod=26, signalperiod=9)
        
        # RSI指标
        rsi = talib.RSI(df['close'], timeperiod=14)
        
        # 布林带
        upper, middle, lower = talib.BBANDS(df['close'], timeperiod=20, nbdevup=2, nbdevdn=2)
        
        signals = []
        
        for i in range(2, len(df)):
            # 做多信号条件
            long_signal = (
                macd[i] > macd_signal[i] and  # MACD金叉
                macd[i-1] <= macd_signal[i-1] and  # 前一根不是金叉
                rsi[i] < 70 and  # RSI不过热
                df['close'][i] > lower[i] and  # 价格在布林带下轨之上
                df['close'][i] < upper[i]  # 价格在布林带上轨之下
            )
            
            # 做空信号条件
            short_signal = (
                macd[i] < macd_signal[i] and  # MACD死叉
                macd[i-1] >= macd_signal[i-1] and  # 前一根不是死叉
                rsi[i] > 30 and  # RSI不超卖
                df['close'][i] < upper[i] and  # 价格在布林带上轨之下
                df['close'][i] > lower[i]  # 价格在布林带下轨之上
            )
            
            signal = 0
            if long_signal:
                signal = 1  # 做多
            elif short_signal:
                signal = -1  # 做空
                
            signals.append(signal)
        
        # 补齐长度
        signals = [0] * 2 + signals
        
        return signals

def backtest_strategy(df, initial_capital=10000):
    """回测函数"""
    strategy = MACD_RSI_BollingerStrategy()
    signals = strategy.calculate_signals(df)
    
    # 模拟交易逻辑
    positions = []
    capital = initial_capital
    trades = []
    
    position = 0  # 0: 无仓位, 1: 多头, -1: 空头
    entry_price = 0
    
    for i in range(len(df)):
        if signals[i] == 1 and position != 1:  # 做多信号
            if position == -1:  # 平空仓
                pnl = (entry_price - df['close'][i]) / entry_price * capital
                capital += pnl
                trades.append({
                    'type': '平空',
                    'price': df['close'][i],
                    'pnl': pnl,
                    'timestamp': df.index[i]
                })
            
            # 开多仓
            position = 1
            entry_price = df['close'][i]
            trades.append({
                'type': '开多',
                'price': entry_price,
                'timestamp': df.index[i]
            })
            
        elif signals[i] == -1 and position != -1:  # 做空信号
            if position == 1:  # 平多仓
                pnl = (df['close'][i] - entry_price) / entry_price * capital
                capital += pnl
                trades.append({
                    'type': '平多',
                    'price': df['close'][i],
                    'pnl': pnl,
                    'timestamp': df.index[i]
                })
            
            # 开空仓
            position = -1
            entry_price = df['close'][i]
            trades.append({
                'type': '开空',
                'price': entry_price,
                'timestamp': df.index[i]
            })
    
    # 计算胜率和收益率
    winning_trades = [t for t in trades if 'pnl' in t and t['pnl'] > 0]
    win_rate = len(winning_trades) / len([t for t in trades if 'pnl' in t]) if trades else 0
    total_return = (capital - initial_capital) / initial_capital * 100
    
    return {
        'strategy_name': strategy.name,
        'total_trades': len([t for t in trades if 'pnl' in t]),
        'win_rate': round(win_rate * 100, 1),
        'total_return': round(total_return, 2),
        'final_capital': round(capital, 2),
        'trades': trades
    }

if __name__ == "__main__":
    # 生成测试数据
    dates = pd.date_range(start='2025-10-01', end='2025-10-07', freq='1H')
    np.random.seed(42)
    prices = 100 + np.cumsum(np.random.randn(len(dates)) * 0.5)
    
    df = pd.DataFrame({
        'open': prices - np.random.randn(len(dates)) * 0.1,
        'high': prices + np.abs(np.random.randn(len(dates)) * 0.2),
        'low': prices - np.abs(np.random.randn(len(dates)) * 0.2),
        'close': prices,
        'volume': np.random.randint(1000, 10000, len(dates))
    }, index=dates)
    
    result = backtest_strategy(df)
    print(f"策略回测结果:")
    print(f"策略名称: {result['strategy_name']}")
    print(f"总交易次数: {result['total_trades']}")
    print(f"胜率: {result['win_rate']}%")
    print(f"总收益率: {result['total_return']}%")
    print(f"最终资金: {result['final_capital']}")