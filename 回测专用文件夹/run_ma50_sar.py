import os
from datetime import datetime, timezone, timedelta

import lightweight_ma50_sar_backtest as m

def format_lines(results, symbols, days):
    lines = [
        "=== MA50 + SAR 轻量策略回测报告 ===",
        f"标的数量: {len(symbols)}",
        f"周期: {days}天",
        ""
    ]
    for r in results:
        if 'error' in r:
            lines.append(f"{r['symbol']}: 错误: {r['error']}")
        else:
            lines.append(f"{r['symbol']}: 交易 {r['total_trades']}, 胜率 {r['win_rate']:.1f}%, 收益率 {r['total_return']:.2f}%")
    return lines

def main():
    symbols = ['FIL-USDT-SWAP','ZRO-USDT-SWAP','WIF-USDT-SWAP','WLD-USDT-SWAP']
    days = 7
    out, results = m.run_ma50_sar_backtest(symbols, days)
    # 固定文件名，确保本地可读
    latest = "backtest_results_ma50_sar_latest.txt"
    lines = format_lines(results, symbols, days)
    with open(latest, "w", encoding="utf-8") as f:
        f.write("\\n".join(lines))
    print(f"报告生成: {latest}")

if __name__ == "__main__":
    main()