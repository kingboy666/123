"""
策略3: ATR + 威廉指标 + 动量组合
特点：波动率控制 + 超买超卖 + 趋势动量
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import talib

class ATR_Williams_MomentumStrategy:
    def __init__(self):
        self.name = "ATR+威廉+动量策略"
        self.description = "波动率控制与动量结合"
        
    def calculate_signals(self, df):
        """计算交易信号"""
        # ATR指标（平均真实波幅）
        atr = talib.ATR(df['high'], df['low'], df['close'], timeperiod=14)
        
        # 威廉指标
        williams = talib.WILLR(df['high'], df['low'], df['close'], timeperiod=14)
        
        # 动量指标
        momentum = talib.MOM(df['close'], timeperiod=10)
        
        # 移动平均线辅助判断
        ma20 = talib.SMA(df['close'], timeperiod=20)
        
        signals = []
        
        for i in range(14, len(df)):
            # 做多信号条件
            long_signal = (
                williams[i] < -80 and  # 威廉指标超卖
                momentum[i] > 0 and  # 动量向上
                df['close'][i] > ma20[i] and  # 价格在20日均线之上
                atr[i] > np.mean(atr[i-5:i])  # ATR放大
            )
            
            # 做空信号条件
            short_signal = (
                williams[i] > -20 and  # 威廉指标超买
                momentum[i] < 0 and  # 动量向下
                df['close'][i] < ma20[i] and  # 价格在20日均线之下
                atr[i] > np.mean(atr[i-5:i])  # ATR放大
            )
            
            signal = 0
            if long_signal:
                signal = 1  # 做多
            elif short_signal:
                signal = -1  # 做空
                
            signals.append(signal)
        
        # 补齐长度
        signals = [0] * 14 + signals
        
        return signals

def backtest_strategy(df, initial_capital=10000):
    """回测函数"""
    strategy = ATR_Williams_MomentumStrategy()
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
    prices = 100 + np.cumsum(np.random.randn(len(dates))) * 0.5
    
    df = pd.DataFrame({
        'open': prices - np.random.randn(len(dates)) * 0.1,
        'high': prices + np.abs(np.random.randn(len(dates))) * 0.2,
        'low': prices - np.abs(np.random.randn(len(dates))) * 0.2,
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