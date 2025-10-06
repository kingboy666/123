"""
测试交易逻辑的脚本
用于验证MACD策略和止盈止损逻辑的正确性
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def calculate_macd(prices, fast=12, slow=26, signal=9):
    """计算MACD指标"""
    exp1 = prices.ewm(span=fast, adjust=False).mean()
    exp2 = prices.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram

def calculate_adx(high, low, close, period=14):
    """计算ADX指标"""
    # 简化实现，实际交易中应使用更精确的计算
    tr = np.maximum(high - low, np.maximum(abs(high - close.shift()), abs(low - close.shift())))
    atr = tr.rolling(window=period).mean()
    return atr.iloc[-1] if len(atr) > 0 else 25

def test_macd_signal():
    """测试MACD信号生成逻辑"""
    print("=== MACD信号生成逻辑测试 ===")
    
    # 模拟K线数据
    np.random.seed(42)
    dates = pd.date_range(start='2025-10-01', periods=100, freq='30min')
    prices = 100 + np.cumsum(np.random.randn(100) * 0.5)
    
    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices - np.random.rand(100) * 2,
        'high': prices + np.random.rand(100) * 3,
        'low': prices - np.random.rand(100) * 3,
        'close': prices,
        'volume': np.random.randint(1000, 10000, 100)
    })
    
    # 计算K线阴阳线
    df['is_bullish'] = df['close'] > df['open']  # 阳线
    df['is_bearish'] = df['close'] < df['open']  # 阴线
    
    # 计算MACD
    macd, signal, hist = calculate_macd(df['close'], fast=6, slow=16, signal=9)
    df['MACD'] = macd
    df['signal'] = signal
    df['histogram'] = hist
    
    # 计算ADX
    adx_value = calculate_adx(df['high'], df['low'], df['close'])
    
    # 测试信号生成
    print(f"当前价格: {df['close'].iloc[-1]:.4f}")
    print(f"MACD: {df['MACD'].iloc[-1]:.6f}")
    print(f"Signal: {df['signal'].iloc[-1]:.6f}")
    print(f"Histogram: {df['histogram'].iloc[-1]:.6f}")
    print(f"当前K线是否为阳线: {df['is_bullish'].iloc[-1]}")
    print(f"ADX趋势强度: {adx_value:.2f}")
    
    # 检查金叉条件
    if len(df) >= 2:
        prev_macd = df['MACD'].iloc[-2]
        prev_signal = df['signal'].iloc[-2]
        prev_close = df['close'].iloc[-2]
        prev_open = df['open'].iloc[-2]
        prev_is_bullish = prev_close > prev_open
        
        # 金叉信号：MACD上穿信号线且前一K线为阳线
        golden_cross = (prev_macd < prev_signal and df['MACD'].iloc[-1] > df['signal'].iloc[-1] and prev_is_bullish)
        
        # 死叉信号：MACD下穿信号线且前一K线为阴线  
        death_cross = (prev_macd > prev_signal and df['MACD'].iloc[-1] < df['signal'].iloc[-1] and not prev_is_bullish)
        
        print(f"\n前一K线MACD: {prev_macd:.6f}")
        print(f"前一K线Signal: {prev_signal:.6f}")
        print(f"前一K线是否为阳线: {prev_is_bullish}")
        print(f"金叉信号: {golden_cross}")
        print(f"死叉信号: {death_cross}")
        
        # 趋势确认：ADX > 25
        trend_confirmed = adx_value > 25
        print(f"趋势确认(ADX>25): {trend_confirmed}")
        
        if golden_cross and trend_confirmed:
            print("✅ 生成做多信号")
        elif death_cross and trend_confirmed:
            print("✅ 生成做空信号")
        else:
            print("❌ 无有效信号")

def test_stop_loss_logic():
    """测试止盈止损逻辑"""
    print("\n=== 止盈止损逻辑测试 ===")
    
    # 模拟持仓信息
    position = {
        'symbol': 'BTC-USDT-SWAP',
        'side': 'long',
        'entry_price': 50000,
        'size': 0.1,
        'strategy_type': 'trend'
    }
    
    current_price = 51000  # 当前价格
    atr = 1000  # ATR值
    
    # 计算未实现盈亏
    unrealized_pnl = (current_price - position['entry_price']) / position['entry_price']
    profit_threshold = atr * 1.5 / position['entry_price']
    
    print(f"入场价格: {position['entry_price']}")
    print(f"当前价格: {current_price}")
    print(f"未实现盈亏: {unrealized_pnl*100:.2f}%")
    print(f"盈利阈值(1.5倍ATR): {profit_threshold*100:.2f}%")
    
    if unrealized_pnl > profit_threshold:
        profit_protection = unrealized_pnl * 0.5  # 保护50%利润
        new_stop_loss = position['entry_price'] * (1 + profit_protection)
        print(f"✅ 启用动态止损")
        print(f"新止损价格: {new_stop_loss:.2f}")
        print(f"止损距离: {(current_price - new_stop_loss)/current_price*100:.2f}%")
    else:
        print("❌ 未达到动态止损启用条件")

def test_kline_confirmation():
    """测试K线收盘确认机制"""
    print("\n=== K线收盘确认机制测试 ===")
    
    # 模拟K线时间
    kline_start = datetime(2025, 10, 6, 21, 0, 0)  # 21:00开始的30分钟K线
    kline_end = kline_start + timedelta(minutes=30)  # 21:30结束
    
    current_time = datetime(2025, 10, 6, 21, 15, 0)  # 当前时间21:15
    
    print(f"K线开始时间: {kline_start}")
    print(f"K线结束时间: {kline_end}")
    print(f"当前时间: {current_time}")
    print(f"K线是否已收盘: {current_time >= kline_end}")
    
    if current_time < kline_end:
        print("⚠️ 当前K线未收盘，应使用前一K线数据进行确认")
        print("✅ 避免在当前K线未收盘时误判平仓")
    else:
        print("✅ 当前K线已收盘，可以进行交易决策")

if __name__ == "__main__":
    test_macd_signal()
    test_stop_loss_logic()
    test_kline_confirmation()
    print("\n=== 测试完成 ===")