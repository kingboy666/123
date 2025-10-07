import re
import os
from collections import defaultdict

# 读取日志文件内容
def read_log_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.readlines()
    except Exception as e:
        print(f"读取文件失败: {e}")
        return []

# 解析日志行
def parse_log_line(line):
    # 匹配策略名称、币种、天数、胜率和收益率的正则表达式
    pattern = r'\[(.*?)\]\s+(\w+-\w+-\w+)\s+(\d+)天:\s+胜率([\d.]+)%\s+收益([-\d.]+)%'
    match = re.search(pattern, line)
    if match:
        strategy = match.group(1)
        symbol = match.group(2)
        days = int(match.group(3))
        win_rate = float(match.group(4))
        return_rate = float(match.group(5))
        return strategy, symbol, days, win_rate, return_rate
    return None

# 分析数据
def analyze_strategies(log_lines):
    # 按币种和策略分组存储结果
    results = defaultdict(lambda: defaultdict(list))
    
    for line in log_lines:
        parsed = parse_log_line(line)
        if parsed:
            strategy, symbol, days, win_rate, return_rate = parsed
            # 跳过胜率为0且收益为0的记录（可能是没有交易的情况）
            if win_rate == 0 and return_rate == 0:
                continue
            results[symbol][strategy].append((days, win_rate, return_rate))
    
    return results

# 找出最高胜率和盈利率
def find_best_results(results):
    best_win_rates = defaultdict(dict)
    best_return_rates = defaultdict(dict)
    
    for symbol, strategies in results.items():
        for strategy, entries in strategies.items():
            # 计算该策略在该币种下的平均胜率和平均收益率
            avg_win_rate = sum(entry[1] for entry in entries) / len(entries)
            avg_return_rate = sum(entry[2] for entry in entries) / len(entries)
            
            # 更新最高胜率
            if strategy not in best_win_rates[symbol] or avg_win_rate > best_win_rates[symbol][strategy][0]:
                best_win_rates[symbol][strategy] = (avg_win_rate, avg_return_rate)
            
            # 更新最高盈利率
            if strategy not in best_return_rates[symbol] or avg_return_rate > best_return_rates[symbol][strategy][1]:
                best_return_rates[symbol][strategy] = (avg_win_rate, avg_return_rate)
    
    return best_win_rates, best_return_rates

# 打印结果
def print_results(best_win_rates, best_return_rates):
    print("=== 各币种最高胜率策略 ===")
    for symbol in sorted(best_win_rates.keys()):
        print(f"\n币种: {symbol}")
        # 按胜率排序
        sorted_strategies = sorted(best_win_rates[symbol].items(), key=lambda x: x[1][0], reverse=True)
        for strategy, (win_rate, return_rate) in sorted_strategies[:3]:  # 显示前3名
            print(f"  策略: {strategy}, 平均胜率: {win_rate:.2f}%, 平均收益率: {return_rate:.2f}%")
    
    print("\n=== 各币种最高收益率策略 ===")
    for symbol in sorted(best_return_rates.keys()):
        print(f"\n币种: {symbol}")
        # 按收益率排序
        sorted_strategies = sorted(best_return_rates[symbol].items(), key=lambda x: x[1][1], reverse=True)
        for strategy, (win_rate, return_rate) in sorted_strategies[:3]:  # 显示前3名
            print(f"  策略: {strategy}, 平均胜率: {win_rate:.2f}%, 平均收益率: {return_rate:.2f}%")

def main():
    log_file = "c:/Users/Administrator/Desktop/新建文件夹/回测专用文件夹/logs.1759783142481.log"
    
    if not os.path.exists(log_file):
        print(f"日志文件不存在: {log_file}")
        return
    
    print(f"正在分析日志文件: {log_file}")
    log_lines = read_log_file(log_file)
    
    if not log_lines:
        print("没有找到有效的日志数据")
        return
    
    results = analyze_strategies(log_lines)
    best_win_rates, best_return_rates = find_best_results(results)
    
    print_results(best_win_rates, best_return_rates)

if __name__ == "__main__":
    main()