# 读取文件内容
with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修复notify_email调用的语法错误
lines = content.split('\n')

# 检查第1500-1510行的内容
print('修复前:')
for i in range(1500, 1510):
    print(f'{i}: {repr(lines[i])}')

# 修复f-string语法错误 - 重新构建notify_email调用
lines[1502] = '                    f"{symbol} 平仓成功",'
lines[1503] = '                    f"{'平多' if position['side']=='long' else '平空'} {size:.6f} @ {current_price:.4f}\\nPnL: {pnl:.4f}\\n策略: {position.get('strategy_type','NA')}"'
lines[1504] = '                )'
lines[1505] = ''  # 清空多余的行
lines[1506] = ''  # 清空多余的行

# 写入修复后的内容
with open('main.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print('修复完成')