# MACD(6,16,9)策略 - Railway部署指南

## 策略概述
基于MACD指标的量化交易策略，在15分钟图上运行，支持FILUSDT、ZROUSDT、WIFUSDT、WLDUSDT四个交易对。

## Railway部署步骤

### 1. 准备GitHub仓库
```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/kingboy666/123.git
git push -u origin main
```

### 2. Railway部署
1. 访问 [Railway](https://railway.app)
2. 连接GitHub账户
3. 选择仓库 `kingboy666/123`
4. 部署项目

### 3. 环境变量配置
在Railway项目设置中配置以下环境变量：
- `OKX_API_KEY`: OKX API密钥
- `OKX_SECRET`: OKX密钥
- `OKX_PASSPHRASE`: OKX密码短语

### 4. 启动策略
部署完成后，策略将自动运行，每15分钟执行一次交易决策。

## 策略特性
- MACD(6,16,9)指标分析
- 20倍杠杆交易
- 80%余额智能分配
- 四个交易对同时监控
- 自动仓位管理

## 监控日志
在Railway的日志界面可以查看策略运行状态和交易记录。