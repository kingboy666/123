#!/usr/bin/env python3
"""
演示版交易系统
无需API配置即可测试交易逻辑
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import random

# 模拟技术指标计算
def calculate_macd(close, fast=6, slow=16, signal=9):
    """模拟MACD指标计算"""
    exp1 = close.ewm(span=fast).mean()
    exp2 = close.ewm(span=slow).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def generate_mock_data(symbol, periods=100):
    """生成模拟K线数据"""
    base_price = random.uniform(10, 1000)
    prices = []
    
    for i in range(periods):
        # 模拟价格波动
        change = random.uniform(-0.05, 0.05)
        base_price *= (1 + change)
        prices.append(base_price)
    
    # 创建DataFrame
    df = pd.DataFrame({
        'timestamp': [datetime.now() - timedelta(minutes=i) for i in range(periods)][::-1],
        'open': [p * random.uniform(0.99, 1.01) for p in prices],
        'high': [p * random.uniform(1.01, 1.03) for p in prices],
        'low': [p * random.uniform(0.97, 0.99) for p in prices],
        'close': prices,
        'volume': [random.uniform(1000, 10000) for _ in range(periods)]
    })
    
    return df

def log_message(level, message):
    """模拟日志记录"""
    timestamp = datetime.now().strftime('[%Y-%m-%d %H:%M:%S]')
    print(f"{timestamp} {level}: {message}")

def generate_signal(symbol, df):
    """生成交易信号（模拟版本）"""
    if len(df) < 20:
        return None
    
    # 计算MACD
    macd_line, signal_line, histogram = calculate_macd(df['close'])
    
    # 获取最新值
    current_macd = macd_line.iloc[-1]
    current_signal = signal_line.iloc[-1]
    prev_macd = macd_line.iloc[-2]
    prev_signal = signal_line.iloc[-2]
    
    # 检查K线是否收盘（模拟）
    current_time = datetime.now()
    kline_close_time = df['timestamp'].iloc[-1] + timedelta(minutes=1)
    seconds_to_close = (kline_close_time - current_time).total_seconds()
    
    # 信号逻辑
    if current_macd > current_signal and prev_macd <= prev_signal:
        if seconds_to_close > 0:
            log_message("DEBUG", f"{symbol} 做多信号条件满足但等待K线收盘 (还需等待{int(seconds_to_close)}秒)")
            return {'type': 'pending_long', 'symbol': symbol, 'close_time': kline_close_time}
        else:
            log_message("INFO", f"{symbol} 做多信号触发")
            return {'type': 'long', 'symbol': symbol}
    
    elif current_macd < current_signal and prev_macd >= prev_signal:
        if seconds_to_close > 0:
            log_message("DEBUG", f"{symbol} 做空信号条件满足但等待K线收盘 (还需等待{int(seconds_to_close)}秒)")
            return {'type': 'pending_short', 'symbol': symbol, 'close_time': kline_close_time}
        else:
            log_message("INFO", f"{symbol} 做空信号触发")
            return {'type': 'short', 'symbol': symbol}
    
    return None

def check_pending_signals(pending_signals):
    """检查待处理信号是否已到K线收盘时间"""
    current_time = datetime.now()
    executed_signals = []
    
    for signal in pending_signals[:]:
        if current_time >= signal['close_time']:
            # K线已收盘，执行信号
            if signal['type'] == 'pending_long':
                executed_signals.append({'type': 'long', 'symbol': signal['symbol']})
                log_message("INFO", f"{signal['symbol']} K线收盘，执行做多信号")
            elif signal['type'] == 'pending_short':
                executed_signals.append({'type': 'short', 'symbol': signal['symbol']})
                log_message("INFO", f"{signal['symbol']} K线收盘，执行做空信号")
            
            pending_signals.remove(signal)
    
    return executed_signals

def demo_trading_loop():
    """演示版交易循环"""
    print("=== 演示版交易系统启动 ===")
    print("无需API配置，模拟交易逻辑测试")
    print("=" * 50)
    
    # 初始化
    symbols = ['BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'AVAX-USDT-SWAP']
    market_data = {}
    pending_signals = []
    position_tracker = {'positions': {}, 'pending_signals': pending_signals}
    
    # 生成初始市场数据
    for symbol in symbols:
        market_data[symbol] = generate_mock_data(symbol)
    
    # 模拟交易循环
    for cycle in range(10):  # 运行10个循环进行演示
        print(f"\n--- 交易循环 {cycle + 1} ---")
        
        executed_this_cycle = []
        
        # 检查待处理信号
        executed_signals = check_pending_signals(pending_signals)
        executed_this_cycle.extend(executed_signals)
        
        # 为每个交易对生成信号
        for symbol in symbols:
            # 更新市场数据（模拟新K线）
            df = market_data[symbol]
            new_price = df['close'].iloc[-1] * random.uniform(0.995, 1.005)
            new_row = {
                'timestamp': datetime.now(),
                'open': df['close'].iloc[-1],
                'high': max(df['close'].iloc[-1], new_price),
                'low': min(df['close'].iloc[-1], new_price),
                'close': new_price,
                'volume': random.uniform(1000, 10000)
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            market_data[symbol] = df.tail(100)  # 保持100个周期
            
            # 生成信号
            signal = generate_signal(symbol, df)
            
            if signal:
                if signal['type'] in ['pending_long', 'pending_short']:
                    pending_signals.append(signal)
                    log_message("DEBUG", f"添加到待处理信号: {signal['symbol']} {signal['type']}")
                else:
                    executed_this_cycle.append(signal)
        
        # 记录本循环执行情况
        if executed_this_cycle:
            for signal in executed_this_cycle:
                log_message("INFO", f"执行交易: {signal['symbol']} {signal['type']}")
        else:
            log_message("INFO", "本循环无交易执行")
        
        # 显示当前状态
        print(f"待处理信号数量: {len(pending_signals)}")
        for signal in pending_signals:
            seconds_left = (signal['close_time'] - datetime.now()).total_seconds()
            print(f"  - {signal['symbol']}: {signal['type']} (剩余{int(seconds_left)}秒)")
        
        # 等待下一循环
        log_message("INFO", "交易循环完成，等待30秒...")
        time.sleep(5)  # 演示时缩短等待时间
    
    print("\n=== 演示结束 ===")
    print("实际使用时需要设置OKX API配置")

if __name__ == "__main__":
    demo_trading_loop()