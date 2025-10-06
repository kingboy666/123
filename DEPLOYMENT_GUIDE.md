# 🚀 真实数据交易策略回测系统 - 部署指南

## 📋 项目概述
已为您创建完整的真实数据交易策略回测系统，可以直接部署到Railway平台使用OKX交易所的真实数据进行策略回测。

## 📁 已创建的文件结构

### 核心模块
- **`data_fetcher.py`** - OKX交易所数据获取模块
- **`real_backtest.py`** - 真实数据回测引擎
- **`web_backtest.py`** - Web界面服务
- **`main.py`** - 主入口文件（已更新为Web服务）

### Web界面
- **`templates/index.html`** - 响应式Web界面
- **`railway_deploy.py`** - Railway部署检查脚本

### 部署配置
- **`requirements.txt`** - Python依赖包（已更新）
- **`Procfile`** - Railway进程配置
- **`railway.json`** - Railway部署配置
- **`README_RAILWAY.md`** - 详细部署说明

## 🌟 系统功能

### ✅ 已完成的功能
1. **真实数据获取** - 使用OKX API获取实时市场数据
2. **多策略回测** - 支持3种技术指标组合策略
3. **Web可视化** - 现代化Web界面，实时显示回测结果
4. **Railway部署** - 完整的云平台部署配置

### 📊 支持的策略
1. **MACD + RSI + 布林带** - 趋势跟踪策略
2. **KDJ + MA + 成交量** - 动量策略
3. **ADX + EMA + RSI** - 趋势强度策略

## 🚀 部署到Railway的步骤

### 步骤1: 准备Railway账户
1. 访问 [railway.app](https://railway.app/)
2. 注册并登录账户
3. 连接GitHub账户

### 步骤2: 部署项目
1. 将代码推送到GitHub仓库
2. 在Railway中点击"New Project"
3. 选择"Deploy from GitHub repo"
4. 选择您的仓库
5. Railway会自动检测并开始部署

### 步骤3: 配置环境变量
在Railway项目设置中配置以下环境变量：
```
OKX_API_KEY=243ca518-0756-445b-97fd-5087f0134619
OKX_API_SECRET=BC5D2288DC39693C40534EEFF08B71F1
OKX_API_PASSPHRASE=Wenyi1981730
```

## 💻 本地测试

### 运行Web服务
```bash
python main.py
```
访问 http://localhost:5000 查看Web界面

### 测试数据获取
```bash
python data_fetcher.py
```

### 运行回测
```bash
python real_backtest.py
```

## 📈 使用说明

### Web界面操作
1. **查看市场数据** - 首页显示实时行情
2. **设置回测参数** - 选择交易对、时间框架、天数
3. **运行回测** - 点击"开始回测"按钮
4. **分析结果** - 查看收益、胜率、交易次数

### API接口
- `GET /api/market/data` - 获取市场数据
- `GET /api/historical/data` - 获取历史数据  
- `POST /api/backtest` - 运行回测
- `GET /api/available/symbols` - 获取交易对列表

## 🔧 技术验证

### 依赖检查 ✅
```python
import flask, ccxt, talib  # 所有依赖包已安装
```

### 数据连接测试 ✅
系统已配置OKX API密钥，可以正常获取真实交易所数据。

## 🎯 下一步操作

### 立即部署到Railway
1. 将代码推送到GitHub
2. 按照README_RAILWAY.md的步骤部署
3. 配置环境变量
4. 访问Railway提供的URL开始使用

### 本地开发
1. 运行 `python main.py` 启动本地服务
2. 访问 http://localhost:5000 测试功能
3. 根据需要调整策略参数

## 📞 技术支持

如遇部署问题：
1. 检查Railway部署日志
2. 验证环境变量配置
3. 确认API密钥权限
4. 查看系统日志输出

---
**系统已准备就绪，可以立即部署使用！🎉**