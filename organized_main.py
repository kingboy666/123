"""
VWAP+MACD+RSI 量化交易策略 - 分类整理版
将原main.py按功能模块重新组织，便于维护和修改
"""

# =================================
# 1. 配置和常量模块
# =================================
import os
import time
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import ccxt
from typing import Dict, List, Optional, Tuple, Any

# API配置
API_KEY = os.getenv('OKX_API_KEY')
SECRET = os.getenv('OKX_SECRET')
PASSPHRASE = os.getenv('OKX_PASSPHRASE')

# 交易对配置 - 热度前10 + 指定4个合约
SYMBOLS = [
    'BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP', 'BNB-USDT-SWAP',
    'XRP-USDT-SWAP', 'DOGE-USDT-SWAP', 'ADA-USDT-SWAP', 'AVAX-USDT-SWAP',
    'SHIB-USDT-SWAP', 'DOT-USDT-SWAP', 'FIL-USDT-SWAP', 'ZRO-USDT-SWAP',
    'WIF-USDT-SWAP', 'WLD-USDT-SWAP'
]

def get_top_symbols_from_exchange(exchange: Optional[Any] = None) -> List[str]:
    """自动从交易所获取热度前10的USDT合约（按24h成交量/信息字段排序），并追加FIL/ZRO/WIF/WLD"""
    try:
        hot = []
        if exchange:
            tickers = exchange.fetch_tickers()
            # 过滤 USDT 合约
            for sym, tk in tickers.items():
                if (sym.endswith('-USDT-SWAP') or sym.endswith(':USDT')) and ('SWAP' in sym or ':' in sym):
                    vol = None
                    # ccxt标准字段或OKX info字段
                    vol = tk.get('quoteVolume') or tk.get('baseVolume')
                    if vol is None and isinstance(tk.get('info'), dict):
                        info = tk['info']
                        # OKX 可能提供 24h成交量（计价币数量）
                        vol = float(info.get('volCcy24h')) if info.get('volCcy24h') else None
                    if vol:
                        hot.append((sym, float(vol)))
            hot.sort(key=lambda x: x[1], reverse=True)
            top10 = [s for s, _ in hot[:10]]
        else:
            top10 = SYMBOLS[:10]
        
        # 统一成 OKX 合约格式 XXX-USDT-SWAP
        def norm_sym(s):
            return s.replace(':USDT', '-USDT-SWAP') if ':USDT' in s else (s if s.endswith('-USDT-SWAP') else s + '-USDT-SWAP')
        base = [norm_sym(s) for s in top10]
        extras = ['FIL-USDT-SWAP', 'ZRO-USDT-SWAP', 'WIF-USDT-SWAP', 'WLD-USDT-SWAP']
        
        # 去重保持顺序
        seen = set()
        symbols = []
        for s in base + extras:
            if s not in seen:
                symbols.append(s)
                seen.add(s)
        
        log_message("INFO", f"自动获取交易对成功: {symbols}")
        return symbols
        
    except Exception as e:
        log_message("WARNING", f"自动获取热门标的失败，使用默认列表: {str(e)}")
        return SYMBOLS[:10] + ['FIL-USDT-SWAP', 'ZRO-USDT-SWAP', 'WIF-USDT-SWAP', 'WLD-USDT-SWAP']
MAX_OPEN_POSITIONS = 10
DEFAULT_LEVERAGE = 3
MAX_LEVERAGE_BTC = 5
MAX_LEVERAGE_ETH = 5
MAX_LEVERAGE_MAJOR = 4  # 主流币种杠杆
MAX_LEVERAGE_MID = 3     # 中等市值币种杠杆
MAX_LEVERAGE_SMALL = 2   # 小市值币种杠杆
TD_MODE = 'cross'  # 全仓模式

# 智能杠杆配置
MAX_LEVERAGE_BTC = 20                        # BTC最大杠杆
MAX_LEVERAGE_ETH = 20                        # ETH最大杠杆
MAX_LEVERAGE_MAJOR = 20                      # 主流币最大杠杆
MAX_LEVERAGE_OTHERS = 20                     # 其他币种最大杠杆
LEVERAGE_MIN = 10                             # 全局最低杠杆
DEFAULT_LEVERAGE = 10                         # 默认杠杆

# 主流币种定义
MAJOR_COINS = ['BNB', 'XRP', 'ADA', 'SOL', 'DOT', 'AVAX', 'DOGE']

# MACD指标配置
MACD_FAST = 8                             # MACD快线周期
MACD_SLOW = 21                            # MACD慢线周期
MACD_SIGNAL = 9                           # MACD信号线周期

# RSI指标配置
RSI_PERIOD = 14                           # RSI计算周期

# 时间框架配置
TIMEFRAME_MAIN = '30m'      # 主图 - 改为M30
TIMEFRAME_CONFIRM = '1h'    # 确认 - 改为1小时

# Bollinger Bands配置
BB_PERIOD = 20
BB_STD = 1.2  # 窄触多30% (原1.5 → 1.2)

# ATR动态止盈止损配置
USE_ATR_DYNAMIC_STOPS = True                 # 启用ATR动态止盈止损
ATR_PERIOD = 14                              # ATR计算周期
ATR_STOP_LOSS_MULTIPLIER = 2.0              # ATR止损倍数
ATR_TAKE_PROFIT_MULTIPLIER = 3.0            # ATR止盈倍数
ATR_TRAILING_ACTIVATION_MULTIPLIER = 1.5    # 移动止盈激活倍数
ATR_TRAILING_CALLBACK_MULTIPLIER = 1.0      # 移动止盈回调倍数
ATR_MIN_MULTIPLIER = 1.0                    # ATR最小倍数
ATR_MAX_MULTIPLIER = 5.0                    # ATR最大倍数

# ADX配置（用于震荡识别，阈值20）
ADX_TREND_THRESHOLD = 20

# 风险管理配置
RISK_PER_TRADE = 0.02                        # 单笔风险2%
MAX_OPEN_POSITIONS = 5                       # 最大持仓数
COOLDOWN_PERIOD = 300                        # 冷却期5分钟
MAX_DAILY_TRADES = 100                        # 每日最大交易次数

# 主循环配置
MAIN_LOOP_DELAY = 10                         # 主循环延迟30秒

# 账户与保证金模式（用于 OKX 下单参数）
ACCOUNT_MODE = 'hedge'                       # 可选 'hedge'（双向持仓）或 'one-way'（单向持仓）
TD_MODE = 'cross'                            # 保证金模式：'cross' 全仓 或 'isolated' 逐仓

# =================================
# 2. 日志和工具函数模块
# =================================
def log_message(level: str, message: str) -> None:
    """统一的日志记录函数"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [{level}] {message}")

def safe_float(value, default=0.0) -> float:
    """安全转换为浮点数"""
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default

def calculate_atr(high: List[float], low: List[float], close: List[float], period: int = 14) -> List[float]:
    """计算平均真实波幅(ATR)"""
    if len(high) < period + 1:
        return [0.0] * len(high)
    
    tr = [0.0] * len(high)
    for i in range(1, len(high)):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i-1]),
            abs(low[i] - close[i-1])
        )
    
    atr = [0.0] * len(high)
    atr[period] = sum(tr[1:period+1]) / period
    for i in range(period+1, len(high)):
        atr[i] = (atr[i-1] * (period-1) + tr[i]) / period
    
    return atr

# =================================
# 3. 交易所接口模块
# =================================
def initialize_exchange() -> Optional[Any]:
    """初始化交易所连接"""
    try:
        # 确保API密钥不为空
        if not API_KEY or not SECRET:
            log_message("ERROR", "API密钥或密钥为空")
            return None
            
        exchange = ccxt.okx({
            'apiKey': API_KEY,
            'secret': SECRET,
            'password': PASSPHRASE or '',
            'sandbox': False,
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })
        log_message("INFO", "交易所连接初始化成功")
        return exchange
    except Exception as e:
        log_message("ERROR", f"交易所初始化失败: {e}")
        return None

def test_api_connection(exchange: ccxt.Exchange) -> bool:
    """测试API连接"""
    try:
        exchange.fetch_balance()
        log_message("SUCCESS", "API连接测试成功")
        return True
    except Exception as e:
        log_message("ERROR", f"API连接测试失败: {e}")
        return False

def get_klines(exchange: Any, symbol: str, timeframe: str = '5m', limit: int = 100) -> Optional[List[Any]]:
    """获取K线数据"""
    if exchange is None:
        log_message("ERROR", "交易所未初始化")
        return None
        
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        return ohlcv
    except Exception as e:
        log_message("ERROR", f"获取{symbol}K线失败: {e}")
        return None

def sync_exchange_positions(exchange: Any) -> None:
    """同步交易所现有持仓"""
    if exchange is None:
        log_message("ERROR", "交易所未初始化")
        return
        
    try:
        positions = exchange.fetch_positions()
        for pos in positions:
            if isinstance(pos, dict) and pos.get('contracts') and float(pos['contracts']) > 0:
                symbol = pos.get('symbol', '')
                side = 'long' if pos.get('side') == 'long' else 'short'
                size = float(pos['contracts'])
                entry_price = float(pos['entryPrice']) if pos.get('entryPrice') else None
                
                if symbol and symbol not in position_tracker['positions']:
                    position_tracker['positions'][symbol] = {
                        'side': side,
                        'size': size,
                        'entry_price': entry_price,
                        'entry_time': datetime.now()
                    }
                    log_message("INFO", f"同步持仓: {symbol} {side} {size}")
    except Exception as e:
        log_message("ERROR", f"同步持仓失败: {e}")

# =================================
# 4. 技术指标计算模块
# =================================
def process_klines(ohlcv: List[Any]) -> Optional[pd.DataFrame]:
    """处理K线数据并计算技术指标"""
    if not ohlcv or len(ohlcv) < 50:
        return None
    
    try:
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        # 计算VWAP
        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
        df['typical_volume'] = df['typical_price'] * df['volume']
        df['cumulative_typical_volume'] = df['typical_volume'].cumsum()
        df['cumulative_volume'] = df['volume'].cumsum()
        df['VWAP'] = df['cumulative_typical_volume'] / df['cumulative_volume']
        
        # 计算MACD
        exp1 = df['close'].ewm(span=MACD_FAST, adjust=False).mean()
        exp2 = df['close'].ewm(span=MACD_SLOW, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['MACD_SIGNAL'] = df['MACD'].ewm(span=MACD_SIGNAL, adjust=False).mean()
        df['MACD_HIST'] = df['MACD'] - df['MACD_SIGNAL']
        
        # 计算RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=RSI_PERIOD).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=RSI_PERIOD).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # 计算ATR
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        df['ATR_14'] = calculate_atr(high, low, close, ATR_PERIOD)
        
        # 成交量MA
        df['vol_ma20'] = df['volume'].rolling(window=20).mean()
        
        return df
    except Exception as e:
        log_message("ERROR", f"处理K线数据失败: {e}")
        return None

# =================================
# 5. 交易信号生成模块
# =================================
def generate_trading_signals(df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
    """生成交易信号"""
    if df is None or len(df) < 20:
        return {'signal': 'hold', 'reason': '数据不足'}
    
    try:
        current = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 基础指标
        vwap = current['VWAP']
        rsi = current['RSI']
        macd = current['MACD']
        macd_sig = current['MACD_SIGNAL']
        close = current['close']
        open_ = current['open']
        volume = current['volume']
        vol_ma20 = current['vol_ma20']
        atr = current['ATR_14']
        
        # 条件判断
        volume_ok = volume >= 0.7 * vol_ma20
        vwap_bias = abs(close - vwap) / vwap > 0.001
        is_bullish = close > open_
        is_bearish = close < open_
        
        # MACD交叉
        golden_cross = (prev['MACD'] <= prev['MACD_SIGNAL']) and (macd > macd_sig)
        death_cross = (prev['MACD'] >= prev['MACD_SIGNAL']) and (macd < macd_sig)
        
        # 多空信号
        long_signal = (golden_cross and close > vwap and rsi > 40 and 
                      vwap_bias and is_bullish and volume_ok)
        
        short_signal = (death_cross and close < vwap and rsi < 60 and 
                       vwap_bias and is_bearish and volume_ok)
        
        if long_signal:
            return {'signal': 'long', 'price': close, 'atr': atr, 'reason': 'MACD金叉+VWAP支撑'}
        elif short_signal:
            return {'signal': 'short', 'price': close, 'atr': atr, 'reason': 'MACD死叉+VWAP阻力'}
        else:
            return {'signal': 'hold', 'reason': '无明确信号'}
            
    except Exception as e:
        log_message("ERROR", f"生成{symbol}交易信号失败: {e}")
        return {'signal': 'hold', 'reason': '计算错误'}

# =================================
# 6. 风险管理模块
# =================================
def calculate_position_size(symbol: str, atr: float, price: float, account_balance: float = 10000) -> float:
    """根据风险计算仓位大小"""
    try:
        # ATR风险模型：每笔交易风险不超过账户的2%
        risk_per_trade = account_balance * 0.02
        atr_value = atr * price if atr and price else 0
        
        if atr_value <= 0:
            return min(account_balance * 0.1, 1000)  # 默认10%仓位，最大1000USDT
        
        # 基于ATR的仓位计算
        position_size = risk_per_trade / atr_value
        
        # 杠杆调整
        leverage = DEFAULT_LEVERAGE
        if 'BTC' in symbol:
            leverage = min(leverage, MAX_LEVERAGE_BTC)
        elif 'ETH' in symbol:
            leverage = min(leverage, MAX_LEVERAGE_ETH)
            
        position_size *= leverage
        
        # 限制最大仓位
        max_position = account_balance * 0.2  # 最大20%仓位
        return min(position_size, max_position, 5000)  # 绝对上限5000USDT
        
    except Exception as e:
        log_message("ERROR", f"计算{symbol}仓位失败: {e}")
        return 1000  # 默认仓位

def check_risk_limits() -> bool:
    """检查风险限制"""
    try:
        # 检查最大持仓数量
        current_positions = len(position_tracker['positions'])
        if current_positions >= MAX_OPEN_POSITIONS:
            log_message("WARNING", f"已达到最大持仓限制: {current_positions}/{MAX_OPEN_POSITIONS}")
            return False
            
        # 检查总风险暴露
        total_exposure = sum(pos['size'] * pos['entry_price'] for pos in position_tracker['positions'].values())
        if total_exposure > 10000:  # 假设账户余额10000
            log_message("WARNING", f"总风险暴露过高: {total_exposure}")
            return False
            
        return True
    except Exception as e:
        log_message("ERROR", f"风险检查失败: {e}")
        return False

# =================================
# 7. 持仓管理模块
# =================================
# 全局持仓跟踪器
position_tracker: Dict[str, Any] = {
    'positions': {},
    'total_trades': 0,
    'total_pnl': 0.0,
    'winning_trades': 0
}

def update_trade_stats(symbol: str, side: str, pnl: float, entry_price: float, exit_price: float) -> None:
    """更新交易统计"""
    if symbol not in position_tracker['positions']:
        return
        
    position_tracker['total_trades'] += 1
    position_tracker['total_pnl'] += pnl
    if pnl > 0:
        position_tracker['winning_trades'] += 1

def check_positions(exchange: Any) -> None:
    """检查并管理现有持仓"""
    if exchange is None:
        log_message("ERROR", "交易所未初始化")
        return
        
    try:
        for symbol, pos in list(position_tracker['positions'].items()):
            try:
                if not isinstance(pos, dict):
                    continue
                    
                side = pos.get('side')
                size = pos.get('size', 0)
                entry_price = pos.get('entry_price')
                
                if size <= 0:
                    del position_tracker['positions'][symbol]
                    continue
                    
                # 获取最新价格和指标
                ohlcv = get_klines(exchange, symbol, '5m', limit=100)
                if not ohlcv:
                    continue
                    
                df = process_klines(ohlcv)
                if df is None or len(df) < 20:
                    continue
                    
                current = df.iloc[-1]
                last_close = current['close']
                atr = current['ATR_14']
                rsi = current['RSI']
                
                # 止盈止损逻辑
                exit_now = False
                exit_partial = False
                partial_ratio = 0.0
                
                # ATR动态止盈止损
                if atr and atr > 0 and entry_price:
                    stop_loss_distance = atr * ATR_STOP_LOSS_MULTIPLIER
                    take_profit_distance = atr * ATR_TAKE_PROFIT_MULTIPLIER
                    
                    if side == 'long':
                        if last_close <= entry_price - stop_loss_distance:
                            exit_now = True
                            log_message("INFO", f"{symbol} 多仓触发ATR止损")
                        elif last_close >= entry_price + take_profit_distance:
                            exit_now = True
                            log_message("INFO", f"{symbol} 多仓触发ATR止盈")
                    elif side == 'short':
                        if last_close >= entry_price + stop_loss_distance:
                            exit_now = True
                            log_message("INFO", f"{symbol} 空仓触发ATR止损")
                        elif last_close <= entry_price - take_profit_distance:
                            exit_now = True
                            log_message("INFO", f"{symbol} 空仓触发ATR止盈")
                
                # 执行平仓
                if exit_now or exit_partial:
                    close_ratio = 1.0 if exit_now else partial_ratio
                    close_size = max(size * close_ratio, 0)
                    
                    if close_size > 0:
                        side_out = 'sell' if side == 'long' else 'buy'
                        try:
                            order = exchange.create_order(
                                symbol,
                                'market',
                                side_out,
                                close_size,
                                None,
                                {'tdMode': TD_MODE, 'posSide': 'long' if side == 'long' else 'short'}
                            )
                            
                            if order:
                                exit_price = last_close
                                pnl = (exit_price - entry_price) * close_size if side == 'long' else (entry_price - exit_price) * close_size
                                
                                log_message("SUCCESS", f"{symbol} 平仓成功: {side_out} {close_size}")
                                update_trade_stats(symbol, side, pnl, entry_price, exit_price)
                                
                                # 更新持仓
                                remain_size = size - close_size
                                if remain_size <= 0:
                                    del position_tracker['positions'][symbol]
                                else:
                                    pos['size'] = remain_size
                                    pos['entry_price'] = exit_price
                                    
                        except Exception as e:
                            log_message("ERROR", f"{symbol} 平仓失败: {e}")
                            
            except Exception as e:
                log_message("ERROR", f"检查{symbol}持仓失败: {e}")
                
    except Exception as e:
        log_message("ERROR", f"持仓检查失败: {e}")

# =================================
# 8. 交易执行模块
# =================================
def execute_trade(exchange: Any, symbol: str, signal: Dict[str, Any]) -> bool:
    """执行交易"""
    if exchange is None:
        log_message("ERROR", "交易所未初始化")
        return False
        
    try:
        if not isinstance(signal, dict) or signal.get('signal') == 'hold':
            return False
            
        # 风险检查
        if not check_risk_limits():
            return False
            
        side = signal['signal']
        price = signal['price']
        atr = signal['atr']
        
        # 计算仓位
        position_size = calculate_position_size(symbol, atr, price)
        
        # 设置杠杆
        leverage = DEFAULT_LEVERAGE
        if 'BTC' in symbol:
            leverage = min(leverage, MAX_LEVERAGE_BTC)
        elif 'ETH' in symbol:
            leverage = min(leverage, MAX_LEVERAGE_ETH)
            
        # 创建订单
        order_side = 'buy' if side == 'long' else 'sell'
        pos_side = 'long' if side == 'long' else 'short'
        
        order = exchange.create_order(
            symbol,
            'market',
            order_side,
            position_size,
            None,
            {
                'tdMode': TD_MODE,
                'posSide': pos_side,
                'leverage': leverage
            }
        )
        
        if order:
            position_tracker['positions'][symbol] = {
                'side': side,
                'size': position_size,
                'entry_price': price,
                'entry_time': datetime.now(),
                'leverage': leverage
            }
            log_message("SUCCESS", f"{symbol} {side}开仓成功: {position_size} @ {price}")
            return True
            
    except Exception as e:
        log_message("ERROR", f"{symbol}交易执行失败: {e}")
        return False
        
    return False

def enhanced_trading_loop(exchange: Any) -> None:
    """增强版交易循环"""
    if exchange is None:
        log_message("ERROR", "交易所未初始化")
        return
        
    log_message("INFO", "启动增强版交易循环")
    
    while True:
        try:
            # 检查并管理现有持仓
            check_positions(exchange)
            
            # 遍历交易对生成信号
            for symbol in SYMBOLS:
                try:
                    # 如果已有该品种持仓，跳过
                    if isinstance(position_tracker['positions'], dict) and symbol in position_tracker['positions']:
                        continue
                        
                    # 获取K线数据
                    ohlcv = get_klines(exchange, symbol, '5m', limit=100)
                    if not ohlcv:
                        continue
                        
                    # 处理指标
                    df = process_klines(ohlcv)
                    if df is None or len(df) < 20:
                        continue
                        
                    # 生成交易信号
                    signal = generate_trading_signals(df, symbol)
                    
                    # 执行交易
                    if signal['signal'] != 'hold':
                        execute_trade(exchange, symbol, signal)
                        
                except Exception as e:
                    log_message("ERROR", f"{symbol}处理失败: {e}")
                    
            # 等待下一周期
            time.sleep(60)  # 1分钟间隔
            
        except KeyboardInterrupt:
            log_message("INFO", "交易循环被用户中断")
            break
        except Exception as e:
            log_message("ERROR", f"交易循环异常: {e}")
            time.sleep(60)

# =================================
# 9. 回测模块
# =================================
def backtest_strategy_5m(exchange: Any, symbol: str, days: int = 14) -> Dict[str, Any]:
    """5分钟回测"""
    if exchange is None:
        log_message("ERROR", "交易所未初始化")
        return {'symbol': symbol, 'trades': [], 'stats': {}}
        
    try:
        limit = max(300, days * 288)  # 5分钟K线，每天288根
        ohlcv = get_klines(exchange, symbol, '5m', limit=limit)
        if not ohlcv:
            return {'symbol': symbol, 'trades': [], 'stats': {}}
            
        df = process_klines(ohlcv)
        if df is None or len(df) < 100:
            return {'symbol': symbol, 'trades': [], 'stats': {}}
            
        trades = []
        position = None
        equity = 10000.0
        size_per_trade = 1000.0
        
        for i in range(20, len(df)):
            row = df.iloc[i]
            prev = df.iloc[i-1]
            
            # 技术指标
            vwap = row['VWAP']
            rsi = row['RSI']
            macd = row['MACD']
            macd_sig = row['MACD_SIGNAL']
            close = row['close']
            open_ = row['open']
            
            # 交叉信号
            golden = (prev['MACD'] <= prev['MACD_SIGNAL']) and (macd > macd_sig)
            death = (prev['MACD'] >= prev['MACD_SIGNAL']) and (macd < macd_sig)
            
            # 平仓逻辑
            if position:
                side = position['side']
                entry_price = position['entry_price']
                
                # 简化平仓条件
                vwap_exit = (side == 'long' and close < vwap) or (side == 'short' and close > vwap)
                rsi_exit = (side == 'long' and rsi > 80) or (side == 'short' and rsi < 20)
                
                if vwap_exit or rsi_exit:
                    exit_price = close
                    pnl = (exit_price - entry_price) if side == 'long' else (entry_price - exit_price)
                    pnl *= DEFAULT_LEVERAGE
                    
                    # 模拟手续费和滑点
                    fee_rate = 0.0005
                    slippage_rate = 0.0005
                    net_ret = (pnl / entry_price) - (fee_rate * 2) - slippage_rate
                    equity += net_ret * size_per_trade
                    
                    trades.append({'side': side, 'entry': entry_price, 'exit': exit_price, 'pnl': pnl})
                    position = None
                    continue
                    
            # 开仓逻辑
            if not position:
                volume_ok = row['volume'] >= 0.7 * row['vol_ma20'] if 'vol_ma20' in row else True
                vwap_bias = abs(close - vwap) / vwap > 0.001
                is_bullish = close > open_
                is_bearish = close < open_
                
                if golden and close > vwap and rsi > 40 and vwap_bias and is_bullish and volume_ok:
                    position = {'side': 'long', 'entry_price': close, 'entry_time': df.index[i]}
                elif death and close < vwap and rsi < 60 and vwap_bias and is_bearish and volume_ok:
                    position = {'side': 'short', 'entry_price': close, 'entry_time': df.index[i]}
                    
        # 统计结果
        wins = sum(1 for t in trades if t['pnl'] > 0)
        total_pnl = sum(t['pnl'] for t in trades)
        win_rate = (wins / len(trades) * 100) if trades else 0.0
        
        return {
            'symbol': symbol,
            'trades': trades,
            'stats': {
                'trades_count': len(trades),
                'win_rate': win_rate,
                'total_pnl': total_pnl,
                'equity': equity
            }
        }
        
    except Exception as e:
        log_message("ERROR", f"{symbol}回测失败: {e}")
        return {'symbol': symbol, 'trades': [], 'stats': {}}

# =================================
# 10. 主程序入口
# =================================
if __name__ == "__main__":
    """主程序入口"""
    try:
        # 初始化交易所
        exchange = initialize_exchange()
        if not exchange:
            log_message("ERROR", "交易所初始化失败")
            exit(1)
            
        # 显示启动信息
        log_message("SUCCESS", "VWAP+MACD+RSI策略交易系统启动")
        log_message("INFO", f"交易对: {len(SYMBOLS)}个")
        log_message("INFO", f"最大持仓: {MAX_OPEN_POSITIONS}")
        log_message("INFO", f"默认杠杆: {DEFAULT_LEVERAGE}x")
        
        # 同步现有持仓
        sync_exchange_positions(exchange)
        
        # 启动交易循环
        enhanced_trading_loop(exchange)
        
    except Exception as e:
        log_message("ERROR", f"系统启动失败: {e}")

# =================================
# 11. 回测功能模块
# =================================
def run_comprehensive_backtest(symbols: Optional[List[str]] = None, days_list: List[int] = [7, 14, 30]) -> Optional[List[Dict[str, Any]]]:
    """运行全面的回测分析"""
    try:
        if symbols is None:
            # 自动从交易所获取热度前10的 USDT 合约（按24h成交量/信息字段排序），并追加 FIL/ZRO/WIF/WLD
            try:
                exchange = initialize_exchange()
                symbols = get_top_symbols_from_exchange(exchange)
                log_message("INFO", f"自动获取回测标的: {symbols[:10]} + extras")
            except Exception as e:
                log_message("WARNING", f"自动获取热门标的失败，使用默认列表: {str(e)}")
                symbols = SYMBOLS[:10] + ['FIL-USDT-SWAP', 'ZRO-USDT-SWAP', 'WIF-USDT-SWAP', 'WLD-USDT-SWAP']
        
        all_results = []
        
        for days in days_list:
            log_message("INFO", f"开始{days}天回测分析...")
            day_results = []
            
            for symbol in symbols:
                result = backtest_strategy_5m(exchange, symbol, days)
                if result:
                    day_results.append(result)
            
            if day_results:
                # 生成该时间周期的回测报告
                report = generate_backtest_report(day_results)
                log_message("INFO", f"{days}天回测结果: {report}")
                all_results.extend(day_results)
        
        # 生成综合报告
        final_report = generate_backtest_report(all_results)
        log_message("INFO", f"综合回测报告: {final_report}")
        
        return all_results
        
    except Exception as e:
        log_message("ERROR", f"全面回测失败: {e}")
        return None

def generate_backtest_report(results: List[Dict[str, Any]]) -> str:
    """生成回测报告"""
    try:
        if not results:
            return "无回测结果"
        
        total_trades = sum(r['stats']['trades_count'] for r in results if r.get('stats'))
        total_pnl = sum(r['stats']['total_pnl'] for r in results if r.get('stats'))
        win_rates = [r['stats']['win_rate'] for r in results if r.get('stats') and r['stats']['trades_count'] > 0]
        avg_win_rate = sum(win_rates) / len(win_rates) if win_rates else 0
        
        report = f"""
=== 回测报告 ===
总交易次数: {total_trades}
总盈亏: {total_pnl:.2f} USDT
平均胜率: {avg_win_rate:.1f}%

各品种表现:
"""
        for result in results:
            if result.get('stats'):
                stats = result['stats']
                report += f"{result['symbol']}: {stats['trades_count']}次交易, 盈亏: {stats['total_pnl']:.2f} USDT, 胜率: {stats['win_rate']:.1f}%"
                report += "
"
        
        return report
        
    except Exception as e:
        log_message("ERROR", f"生成回测报告失败: {e}")
        return "生成回测报告失败"