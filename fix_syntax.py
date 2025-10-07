# 读取文件内容
with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修复第1503-1505行的f-string语法错误
lines = content.split('\n')

# 检查第1503-1505行的内容
print('修复前:')
print('第1503行:', repr(lines[1502]))
print('第1504行:', repr(lines[1503])) 
print('第1505行:', repr(lines[1504]))

# 修复f-string语法错误
lines[1502] = '                    f\"{\'平多\' if position[\'side\']==\'long\' else \'平空\'} {size:.6f} @ {current_price:.4f}\\nPnL: {pnl:.4f}\\n策略: {position.get(\'strategy_type\',\'NA\')}\"'
lines[1503] = ''  # 清空第1504行
lines[1504] = ''  # 清空第1505行

# 写入修复后的内容
with open('main.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print('修复完成')