"""
批量回测脚本 - 同时测试3种指标组合策略
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import sys
import os

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(__file__))

# 导入策略模块
from 策略1_MACD_RSI_布林带 import backtest_strategy as backtest_strategy1
from 策略2_KDJ_MA_成交量 import backtest_strategy as backtest_strategy2
from 策略3_ADX_EMA_RSI import ADX_EMA_RSI策略

def generate_test_data():
    """生成测试数据"""
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
    
    return df

def run_batch_backtest():
    """运行批量回测"""
    print("开始批量回测...")
    print("=" * 60)
    
    # 生成测试数据
    df = generate_test_data()
    
    # 策略列表
    strategies = [
        ("策略1: MACD+RSI+布林带", backtest_strategy1),
        ("策略2: KDJ+MA+成交量", backtest_strategy2),
        ("策略3: ADX+EMA+RSI", lambda df: ADX_EMA_RSI策略().backtest(df))
    ]
    
    results = []
    
    for strategy_name, strategy_func in strategies:
        print(f"\n正在回测: {strategy_name}")
        print("-" * 40)
        
        try:
            result = strategy_func(df)
            results.append(result)
            
            print(f"策略名称: {result['strategy_name']}")
            print(f"总交易次数: {result['total_trades']}")
            print(f"胜率: {result['win_rate']}%")
            print(f"总收益率: {result['total_return']}%")
            print(f"最终资金: {result['final_capital']}")
            
        except Exception as e:
            print(f"回测失败: {e}")
            results.append({
                'strategy_name': strategy_name,
                'total_trades': 0,
                'win_rate': 0,
                'total_return': 0,
                'final_capital': 10000,
                'error': str(e)
            })
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("批量回测汇总结果:")
    print("=" * 60)
    
    for i, result in enumerate(results):
        print(f"\n{i+1}. {result['strategy_name']}")
        print(f"   交易次数: {result['total_trades']}")
        print(f"   胜率: {result['win_rate']}%")
        print(f"   收益率: {result['total_return']}%")
        print(f"   最终资金: {result['final_capital']}")
        
        if 'error' in result:
            print(f"   错误: {result['error']}")
    
    # 找出最佳策略
    valid_results = [r for r in results if 'error' not in r and r['total_trades'] > 0]
    if valid_results:
        best_strategy = max(valid_results, key=lambda x: x['total_return'])
        print(f"\n最佳策略: {best_strategy['strategy_name']}")
        print(f"最佳收益率: {best_strategy['total_return']}%")
    
    return results

if __name__ == "__main__":
    run_batch_backtest()