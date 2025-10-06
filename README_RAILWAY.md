# 🚀 Railway 部署指南

## 项目概述
这是一个基于真实交易所数据的交易策略回测系统，使用OKX交易所的实时数据进行策略分析和回测。

## 📋 部署步骤

### 1. 准备Railway账户
- 访问 [Railway](https://railway.app/) 并注册账户
- 连接您的GitHub仓库或直接部署

### 2. 设置环境变量
在Railway项目的环境变量中设置以下参数：

```env
OKX_API_KEY=您的OKX API密钥
OKX_API_SECRET=您的OKX API秘钥
OKX_API_PASSPHRASE=您的OKX API密码短语
```

### 3. 部署配置
项目已包含以下部署配置文件：

- `railway.json` - Railway部署配置
- `Procfile` - 进程启动配置
- `requirements.txt` - Python依赖包
- `runtime.txt` - Python版本指定

### 4. 部署流程
1. 将代码推送到GitHub仓库
2. 在Railway中连接您的GitHub仓库
3. Railway会自动检测并开始部署
4. 部署完成后，Railway会提供一个公开访问URL

## 🌐 系统功能

### Web界面功能
- **实时市场数据** - 显示主要加密货币的实时价格和涨跌幅
- **策略回测** - 支持多种技术指标组合的策略回测
- **可视化图表** - 交互式图表展示回测结果
- **参数配置** - 灵活设置回测参数和时间范围

### 支持的策略
1. **MACD + RSI + 布林带** - 趋势跟踪策略
2. **KDJ + MA + 成交量** - 动量策略  
3. **ADX + EMA + RSI** - 趋势强度策略

## 📊 数据源
系统使用OKX交易所的实时数据：
- 实时行情数据
- 历史K线数据（1小时、4小时、日线）
- 支持主流交易对（BTC/USDT, ETH/USDT, AVAX/USDT等）

## 🔧 技术栈
- **后端**: Python + Flask
- **前端**: HTML + CSS + JavaScript + ECharts
- **数据**: OKX API + CCXT库
- **分析**: TA-Lib技术指标库
- **部署**: Railway平台

## 📈 使用说明

### 访问Web界面
部署成功后，访问Railway提供的URL即可使用系统：

1. **查看市场数据** - 首页显示实时行情
2. **设置回测参数** - 选择交易对、时间框架、回测天数
3. **运行回测** - 点击"开始回测"按钮
4. **分析结果** - 查看各策略的收益、胜率、交易次数

### API接口
系统提供以下REST API接口：

```http
GET /api/market/data          # 获取市场数据
GET /api/available/symbols    # 获取可交易品种
GET /api/historical/data      # 获取历史数据
POST /api/backtest           # 运行回测
```

## 🛠️ 故障排除

### 常见问题

1. **环境变量错误**
   - 检查OKX API密钥是否正确
   - 确保API有足够的权限

2. **依赖安装失败**
   - 检查Python版本兼容性
   - 确认所有依赖包在requirements.txt中

3. **数据获取失败**
   - 检查网络连接
   - 验证OKX API的可用性

### 日志查看
在Railway控制台可以查看实时日志，帮助诊断问题。

## 🔒 安全说明
- API密钥通过环境变量安全存储
- 不存储任何敏感数据
- 所有数据传输使用HTTPS加密

## 📞 支持
如遇部署问题，请检查：
1. Railway部署日志
2. 环境变量配置
3. API密钥权限

---
**Happy Trading! 🎯**