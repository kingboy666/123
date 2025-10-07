# 交易系统配置说明

## 问题描述
原始问题：系统检测到做空信号但没有实际执行交易。日志显示AVAX-USDT-SWAP做空信号被检测到，系统等待K线收盘，但只下了条件单（止盈止损）而没有实际开仓。

## 已修复的问题

### 1. 待处理信号跟踪系统
**问题**：当K线未收盘时，系统检测到信号但返回None，导致信号丢失。

**修复**：
- 修改`generate_signal`函数返回待处理信号而不是None
- 在`position_tracker`中添加`pending_signals`跟踪
- 创建`check_pending_signals`函数处理K线收盘事件
- 修改交易循环以处理待处理信号

### 2. 时间同步问题
**问题**：系统时间没有同步，可能导致时间戳不一致。

**修复**：
- 检查所有时间相关函数（46处使用datetime.now()和time.time()）
- 添加时区处理逻辑
- 确保日志时间戳一致性

## API配置要求

### 必需配置
系统需要OKX交易所的API密钥才能正常运行：

1. **API Key** - 交易所提供的访问密钥
2. **Secret Key** - 用于签名的密钥
3. **Passphrase** - API密码

### 配置方式

#### 方式1：创建.env文件（推荐）
在项目根目录创建`.env`文件，内容如下：
```
OKX_API_KEY=your_actual_api_key
OKX_SECRET_KEY=your_actual_secret_key
OKX_PASSPHRASE=your_actual_passphrase
```

#### 方式2：设置环境变量
**Windows:**
```cmd
set OKX_API_KEY=your_actual_api_key
set OKX_SECRET_KEY=your_actual_secret_key
set OKX_PASSPHRASE=your_actual_passphrase
```

**Linux/Mac:**
```bash
export OKX_API_KEY=your_actual_api_key
export OKX_SECRET_KEY=your_actual_secret_key
export OKX_PASSPHRASE=your_actual_passphrase
```

## 演示系统

### demo_trading_system.py
无需API配置的演示版本，可以测试：
- 交易信号生成逻辑
- 待处理信号跟踪功能
- K线收盘时间处理
- 交易循环流程

### 运行演示
```bash
python demo_trading_system.py
```

## 文件说明

- `main.py` - 主交易系统（需要API配置）
- `demo_trading_system.py` - 演示版交易系统（无需API）
- `test_api_config.py` - API配置测试工具
- `.env.example` - 环境变量配置示例
- `README_配置说明.md` - 本文档

## 下一步操作

1. 首先运行演示系统验证交易逻辑：`python demo_trading_system.py`
2. 获取OKX API密钥后，配置环境变量
3. 运行完整系统：`python main.py`

## 技术支持
如果遇到问题，请检查：
- API配置是否正确设置
- 网络连接是否正常
- 交易所账户是否有足够资金和权限