import ccxt
import pandas as pd
from datetime import datetime, timedelta, timezone
import time

try:
    import talib
except ImportError:
    talib = None

def _normalize_symbol_for_exchange(sym: str, ex) -> str:
    """将符号转换为对应交易所的可用格式"""
    if isinstance(ex, ccxt.binance):
        # Binance 使用 BTC/USDT 格式
        if '-USDT-SWAP' in sym:
            return sym.replace('-USDT-SWAP', '/USDT')
        if ':' in sym:
            return sym.replace(':USDT', '/USDT')
        if '-' in sym and sym.endswith('-USDT'):
            base = sym.split('-')[0]
            return f"{base}/USDT"
        if '/' in sym:
            return sym
        return f"{sym}/USDT" if not sym.endswith('/USDT') else sym
    elif isinstance(ex, ccxt.okx):
        # OKX 合约使用 XXX-USDT-SWAP
        if ':USDT' in sym:
            return sym.replace(':USDT', '-USDT-SWAP')
        if '/USDT' in sym:
            base = sym.split('/USDT')[0]
            return f"{base}-USDT-SWAP"
        return sym if sym.endswith('-USDT-SWAP') else f"{sym}-USDT-SWAP"
    return sym

def fetch_ohlcv_public(symbol: str, timeframe: str = '30m', days: int = 7) -> pd.DataFrame:
    """使用公共行情客户端抓取OHLCV，不需要API密钥"""
    # 优先OKX，失败回退Binance
    try:
        ex = ccxt.okx()
    except Exception:
        ex = ccxt.binance()
    sym = _normalize_symbol_for_exchange(symbol, ex)
    limit = days * 48  # 30m * 48 根/天
    data = ex.fetch_ohlcv(sym, timeframe=timeframe, limit=limit)
    if not data or len(data) == 0:
        raise Exception(f"公共行情为空: {sym}")
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def backtest_ma50_sar(symbol: str, days: int = 7, initial_balance: float = 10000.0) -> dict:
    """轻量策略回测：MA50 上方 SAR<close 做多，SAR翻到上方立即平仓；MA50 下方 SAR>close 做空，SAR翻到下方立即平仓"""
    df = fetch_ohlcv_public(symbol, '30m', days)
    if len(df) < 60:
        return {
            'symbol': symbol,
            'days': days,
            'error': '数据不足'
        }

    # 指标
    df['ma50'] = df['close'].rolling(window=50, min_periods=50).mean()
    if talib is None:
        # 简易近似：用前一根极值替代（非标准SAR，仅兜底），建议安装TA-Lib获得准确SAR
        prev_min = df['low'].rolling(window=5, min_periods=1).min()
        prev_max = df['high'].rolling(window=5, min_periods=1).max()
        # 当接近低点时视为SAR在下；接近高点时视为SAR在上（仅兜底用）
        df['sar'] = (prev_min + prev_max) / 2.0
    else:
        df['sar'] = talib.SAR(df['high'].values, df['low'].values, acceleration=0.02, maximum=0.2)

    position = None  # 'long' | 'short' | None
    entry_price = 0.0
    entry_time = None
    size = 0.0  # 1x 仓位（轻量）
    balance = initial_balance
    trades = []

    for i in range(len(df)):
        row = df.iloc[i]
        price = float(row['close'])
        ma50 = row['ma50']
        sar = row['sar']

        # 平仓逻辑：SAR反转立即平仓
        if position == 'long':
            if sar >= price:
                exit_price = price
                pnl = (exit_price - entry_price) * size
                balance += pnl
                trades.append({'side': 'close_long', 'entry': entry_price, 'exit': exit_price, 'pnl': pnl,
                               'entry_time': entry_time, 'exit_time': row['timestamp']})
                position = None
                size = 0.0
                entry_price = 0.0
                entry_time = None
        elif position == 'short':
            if sar <= price:
                exit_price = price
                pnl = (entry_price - exit_price) * size
                balance += pnl
                trades.append({'side': 'close_short', 'entry': entry_price, 'exit': exit_price, 'pnl': pnl,
                               'entry_time': entry_time, 'exit_time': row['timestamp']})
                position = None
                size = 0.0
                entry_price = 0.0
                entry_time = None

        # 开仓逻辑（无持仓时）
        if position is None and pd.notna(ma50):
            if price > ma50 and sar < price:
                # MA50上方，SAR在K线下，开多
                position = 'long'
                entry_price = price
                entry_time = row['timestamp']
                size = (balance * 0.8) / price  # 1x 轻量
                trades.append({'side': 'open_long', 'price': entry_price, 'timestamp': entry_time})
            elif price < ma50 and sar > price:
                # MA50下方，SAR在K线上，开空
                position = 'short'
                entry_price = price
                entry_time = row['timestamp']
                size = (balance * 0.8) / price
                trades.append({'side': 'open_short', 'price': entry_price, 'timestamp': entry_time})

    # 若最后仍有持仓，按最后一根价格强制平仓
    if position == 'long':
        exit_price = float(df['close'].iloc[-1])
        pnl = (exit_price - entry_price) * size
        balance += pnl
        trades.append({'side': 'close_long', 'entry': entry_price, 'exit': exit_price, 'pnl': pnl,
                       'entry_time': entry_time, 'exit_time': df['timestamp'].iloc[-1]})
    elif position == 'short':
        exit_price = float(df['close'].iloc[-1])
        pnl = (entry_price - exit_price) * size
        balance += pnl
        trades.append({'side': 'close_short', 'entry': entry_price, 'exit': exit_price, 'pnl': pnl,
                       'entry_time': entry_time, 'exit_time': df['timestamp'].iloc[-1]})

    # 统计
    closed = [t for t in trades if t.get('pnl') is not None]
    total_trades = len(closed)
    wins = len([t for t in closed if t['pnl'] > 0])
    losses = len([t for t in closed if t['pnl'] < 0])
    win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
    total_return = ((balance - initial_balance) / initial_balance * 100.0) if initial_balance > 0 else 0.0

    return {
        'symbol': symbol,
        'days': days,
        'initial_balance': initial_balance,
        'final_balance': balance,
        'total_return': total_return,
        'total_trades': total_trades,
        'win_rate': win_rate,
        'trades': closed
    }

def run_ma50_sar_backtest(symbols=None, days=7, initial_balance=10000.0):
    """运行 MA50+SAR 轻量策略回测，默认只跑 FIL/ZRO/WIF/WLD，周期7天"""
    if symbols is None:
        symbols = ['FIL-USDT-SWAP', 'ZRO-USDT-SWAP', 'WIF-USDT-SWAP', 'WLD-USDT-SWAP']
    results = []
    for sym in symbols:
        try:
            r = backtest_ma50_sar(sym, days, initial_balance)
        except Exception as e:
            r = {'symbol': sym, 'days': days, 'error': str(e)}
        results.append(r)

    # 生成报告
    ts = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d_%H%M%S")
    out = f"backtest_results_ma50_sar_{ts}.txt"
    lines = [
        "=== MA50 + SAR 轻量策略回测报告 ===",
        f"标的数量: {len(symbols)}",
        f"周期: {days}天",
        ""
    ]
    for r in results:
        if 'error' in r:
            lines.append(f"{r['symbol']}: 错误: {r['error']}")
            continue
        lines.extend([
            f"{r['symbol']}: 交易 {r['total_trades']}, 胜率 {r['win_rate']:.1f}%, 收益率 {r['total_return']:.2f}%"
        ])
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    latest = "backtest_results_ma50_sar_latest.txt"
    with open(latest, "w", encoding="utf-8") as f2:
        f2.write("\n".join(lines))
    return out, results

if __name__ == "__main__":
    path, _ = run_ma50_sar_backtest()
    print(f"报告生成: {path}")