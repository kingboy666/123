import pandas as pd
import numpy as np
import talib

class CCI_OBV_抛物线策略:
    def __init__(self):
        self.name = "CCI+OBV+抛物线策略"
        
    def calculate_signals(self, df):
        """计算CCI、OBV和抛物线指标信号"""
        # CCI指标 (商品通道指数)
        cci = talib.CCI(df['high'], df['low'], df['close'], timeperiod=14)
        
        # OBV指标 (能量潮)
        obv = talib.OBV(df['close'], df['volume'])
        obv_ma = talib.MA(obv, timeperiod=20)
        
        # 抛物线指标 (SAR)
        sar = talib.SAR(df['high'], df['low'], acceleration=0.02, maximum=0.2)
        
        # 移动平均线
        ma20 = talib.MA(df['close'], timeperiod=20)
        
        signals = []
        for i in range(20, len(df)):
            # 做多信号: CCI从超卖区反弹 + OBV上涨 + 价格在SAR之上
            long_signal = (
                cci[i] > -150 and cci[i-1] < -150 and  # CCI从超卖区反弹
                obv[i] > obv[i-1] and  # OBV上涨
                df['close'][i] > sar[i]  # 价格在SAR之上
            )
            
            # 做空信号: CCI从超买区回落 + OBV下跌 + 价格在SAR之下
            short_signal = (
                cci[i] < 150 and cci[i-1] > 150 and  # CCI从超买区回落
                obv[i] < obv[i-1] and  # OBV下跌
                df['close'][i] < sar[i]  # 价格在SAR之下
            )
            
            signals.append({
                'timestamp': df.index[i],
                'long_signal': long_signal,
                'short_signal': short_signal,
                'cci': cci[i],
                'obv': obv[i],
                'obv_ma': obv_ma[i],
                'sar': sar[i],
                'ma20': ma20[i],
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
                    # 多头平仓: 价格跌破SAR或CCI超买
                    exit_condition = (
                        signal['close'] < signal['sar'] or  # 价格跌破SAR
                        signal['cci'] > 100  # CCI超买
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
                    # 空头平仓: 价格突破SAR或CCI超卖
                    exit_condition = (
                        signal['close'] > signal['sar'] or  # 价格突破SAR
                        signal['cci'] < -100  # CCI超卖
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
    strategy = CCI_OBV_抛物线策略()
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