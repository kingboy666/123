import pandas as pd
import numpy as np
import talib

class ADX_EMA_RSI策略:
    def __init__(self):
        self.name = "ADX+EMA+RSI策略"
        
    def calculate_signals(self, df):
        """计算ADX、EMA和RSI指标信号"""
        # ADX指标 (平均趋向指数)
        adx = talib.ADX(df['high'], df['low'], df['close'], timeperiod=14)
        
        # EMA指标 (指数移动平均线)
        ema_fast = talib.EMA(df['close'], timeperiod=12)
        ema_slow = talib.EMA(df['close'], timeperiod=26)
        
        # RSI指标 (相对强弱指数)
        rsi = talib.RSI(df['close'], timeperiod=14)
        
        signals = []
        for i in range(26, len(df)):
            # 趋势判断
            trend_strength = adx[i] > 25  # ADX大于25表示强趋势
            
            # 做多信号: 强趋势 + EMA金叉 + RSI不超买
            long_signal = (
                trend_strength and  # 强趋势
                ema_fast[i] > ema_slow[i] and ema_fast[i-1] <= ema_slow[i-1] and  # EMA金叉
                rsi[i] > 50 and rsi[i] < 70  # RSI在50-70之间
            )
            
            # 做空信号: 强趋势 + EMA死叉 + RSI不超卖
            short_signal = (
                trend_strength and  # 强趋势
                ema_fast[i] < ema_slow[i] and ema_fast[i-1] >= ema_slow[i-1] and  # EMA死叉
                rsi[i] < 50 and rsi[i] > 30  # RSI在30-50之间
            )
            
            signals.append({
                'timestamp': df.index[i],
                'long_signal': long_signal,
                'short_signal': short_signal,
                'adx': adx[i],
                'ema_fast': ema_fast[i],
                'ema_slow': ema_slow[i],
                'rsi': rsi[i],
                'close': df['close'][i]
            })
        
        return pd.DataFrame(signals)
    
    def backtest(self, df, capital=10000):
        """回测策略"""
        signals_df = self.calculate_signals(df)
        
        trades = []
        position = None
        entry_price = 0
        entry_index = 0
        
        for i, signal in signals_df.iterrows():
            if position is None:
                # 开仓逻辑
                if signal['long_signal']:
                    position = 'long'
                    entry_price = signal['close']
                    entry_index = i
                    trades.append({
                        'type': 'long',
                        'entry_time': signal['timestamp'],
                        'entry_price': entry_price,
                        'exit_time': None,
                        'exit_price': None,
                        'pnl': 0
                    })
                elif signal['short_signal']:
                    position = 'short'
                    entry_price = signal['close']
                    entry_index = i
                    trades.append({
                        'type': 'short',
                        'entry_time': signal['timestamp'],
                        'entry_price': entry_price,
                        'exit_time': None,
                        'exit_price': None,
                        'pnl': 0
                    })
            else:
                # 平仓逻辑
                if position == 'long':
                    # 多头平仓: EMA死叉或RSI超买
                    exit_condition = (
                        signal['ema_fast'] < signal['ema_slow'] or  # EMA死叉
                        signal['rsi'] > 70 or  # RSI超买
                        signal['adx'] < 20  # 趋势减弱
                    )
                    if exit_condition:
                        pnl = (signal['close'] - entry_price) / entry_price * capital
                        trades[-1].update({
                            'exit_time': signal['timestamp'],
                            'exit_price': signal['close'],
                            'pnl': pnl
                        })
                        position = None
                
                elif position == 'short':
                    # 空头平仓: EMA金叉或RSI超卖
                    exit_condition = (
                        signal['ema_fast'] > signal['ema_slow'] or  # EMA金叉
                        signal['rsi'] < 30 or  # RSI超卖
                        signal['adx'] < 20  # 趋势减弱
                    )
                    if exit_condition:
                        pnl = (entry_price - signal['close']) / entry_price * capital
                        trades[-1].update({
                            'exit_time': signal['timestamp'],
                            'exit_price': signal['close'],
                            'pnl': pnl
                        })
                        position = None
        
        # 计算统计指标
        completed_trades = [t for t in trades if t['exit_time'] is not None]
        total_trades = len(completed_trades)
        
        if total_trades > 0:
            winning_trades = len([t for t in completed_trades if t['pnl'] > 0])
            win_rate = winning_trades / total_trades * 100
            total_return = sum(t['pnl'] for t in completed_trades)
            final_capital = capital + total_return
        else:
            win_rate = 0
            total_return = 0
            final_capital = capital
        
        return {
            'strategy_name': self.name,
            'total_trades': total_trades,
            'win_rate': win_rate,
            'total_return': total_return,
            'final_capital': final_capital,
            'trades': completed_trades
        }

def generate_test_data():
    """生成测试数据"""
    np.random.seed(42)
    dates = pd.date_range(start='2025-10-01', end='2025-10-07', freq='1h')
    
    # 生成随机价格数据
    prices = [100]
    for i in range(1, len(dates)):
        change = np.random.normal(0, 0.5)  # 0.5%的波动
        prices.append(prices[-1] * (1 + change / 100))
    
    # 生成成交量数据
    volumes = np.random.randint(1000, 10000, len(dates))
    
    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p * (1 + np.random.uniform(0, 0.02)) for p in prices],
        'low': [p * (1 - np.random.uniform(0, 0.02)) for p in prices],
        'close': prices,
        'volume': volumes
    })
    df.set_index('timestamp', inplace=True)
    
    return df

if __name__ == "__main__":
    # 生成测试数据
    df = generate_test_data()
    
    # 创建策略实例并回测
    strategy = ADX_EMA_RSI策略()
    results = strategy.backtest(df)
    
    # 输出结果
    print(f"策略名称: {results['strategy_name']}")
    print(f"总交易次数: {results['total_trades']}")
    print(f"胜率: {results['win_rate']:.1f}%")
    print(f"总收益率: {results['total_return']:.2f}%")
    print(f"最终资金: {results['final_capital']:.2f}")
    
    # 显示交易详情
    if results['trades']:
        print("\n交易详情:")
        for i, trade in enumerate(results['trades'][:5], 1):  # 只显示前5笔交易
            print(f"交易{i}: {trade['type']} | 入场: {trade['entry_price']:.2f} | "
                  f"出场: {trade['exit_price']:.2f} | 盈亏: {trade['pnl']:.2f}")