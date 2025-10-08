#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MACD策略实现 - RAILWALL平台版本
25倍杠杆，无限制交易，带挂单识别和状态同步
增加胜率统计和盈亏显示
"""
import time
import logging
import datetime
import os
import json
from typing import Dict, Any, List, Optional
import pytz

import ccxt
import pandas as pd
import numpy as np

# 配置日志 - 使用中国时区和UTF-8编码
class ChinaTimeFormatter(logging.Formatter):
    """中国时区的日志格式化器"""
    def formatTime(self, record, datefmt=None):
        dt = datetime.datetime.fromtimestamp(record.created, tz=pytz.timezone('Asia/Shanghai'))
        if datefmt:
            s = dt.strftime(datefmt)
        else:
            s = dt.strftime('%Y-%m-%d %H:%M:%S')
        return s

# 配置日志 - 确保RAILWAY平台兼容
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)
formatter = ChinaTimeFormatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False  # 防止重复日志

class TradingStats:
    """交易统计类"""
    def __init__(self, stats_file: str = 'trading_stats.json'):
        self.stats_file = stats_file
        self.stats = {
            'total_trades': 0,
            'win_trades': 0,
            'loss_trades': 0,
            'total_pnl': 0.0,
            'total_win_pnl': 0.0,
            'total_loss_pnl': 0.0,
            'trades_history': []
        }
        self.load_stats()
    
    def load_stats(self):
        """加载统计数据"""
        try:
            if os.path.exists(self.stats_file):
                with open(self.stats_file, 'r') as f:
                    self.stats = json.load(f)
                logger.info(f"✅ 加载历史统计数据：总交易{self.stats['total_trades']}笔")
        except Exception as e:
            logger.warning(f"⚠️ 加载统计数据失败: {e}，使用新数据")
    
    def save_stats(self):
        """保存统计数据"""
        try:
            with open(self.stats_file, 'w') as f:
                json.dump(self.stats, f, indent=2)
        except Exception as e:
            logger.error(f"❌ 保存统计数据失败: {e}")
    
    def add_trade(self, symbol: str, side: str, pnl: float):
        """添加交易记录"""
        self.stats['total_trades'] += 1
        self.stats['total_pnl'] += pnl
        
        if pnl > 0:
            self.stats['win_trades'] += 1
            self.stats['total_win_pnl'] += pnl
        else:
            self.stats['loss_trades'] += 1
            self.stats['total_loss_pnl'] += pnl
        
        # 添加交易历史 - 使用北京时间
        china_tz = pytz.timezone('Asia/Shanghai')
        trade_record = {
            'timestamp': datetime.datetime.now(china_tz).strftime('%Y-%m-%d %H:%M:%S'),
            'symbol': symbol,
            'side': side,
            'pnl': round(pnl, 4)
        }
        self.stats['trades_history'].append(trade_record)
        
        # 只保留最近100条记录
        if len(self.stats['trades_history']) > 100:
            self.stats['trades_history'] = self.stats['trades_history'][-100:]
        
        self.save_stats()
    
    def get_win_rate(self) -> float:
        """计算胜率"""
        if self.stats['total_trades'] == 0:
            return 0.0
        return (self.stats['win_trades'] / self.stats['total_trades']) * 100
    
    def get_summary(self) -> str:
        """获取统计摘要"""
        win_rate = self.get_win_rate()
        return (f"📊 交易统计: 总计{self.stats['total_trades']}笔 | "
                f"胜{self.stats['win_trades']}笔 负{self.stats['loss_trades']}笔 | "
                f"胜率{win_rate:.1f}% | "
                f"总盈亏{self.stats['total_pnl']:.2f}U | "
                f"盈利{self.stats['total_win_pnl']:.2f}U 亏损{self.stats['total_loss_pnl']:.2f}U")

class MACDStrategy:
    """MACD策略类"""
    def __init__(self, api_key: str, secret_key: str, passphrase: str):
        """初始化策略"""
        # 交易所配置
        self.exchange = ccxt.okx({
            'apiKey': api_key,
            'secret': secret_key,
            'password': passphrase,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',  # 设置默认交易类型为永续合约
                'types': ['swap'],      # 仅加载/使用 swap 市场，避免解析其他类型导致的空base/quote
            }
        })
        
        # OKX统一参数（强制使用SWAP场景）
        self.okx_params = {'instType': 'SWAP'}
        
        # 交易对配置 - 小币种
        self.symbols = [
            'FIL/USDT:USDT',
            'ZRO/USDT:USDT',
            'WIF/USDT:USDT',
            'WLD/USDT:USDT'
        ]
        
        # 时间周期 - 15分钟
        self.timeframe = '15m'
        
        # MACD参数
        self.fast_period = 6
        self.slow_period = 16
        self.signal_period = 9
        
        # 杠杆配置 - 分币种设置
        self.symbol_leverage: Dict[str, int] = {
            'FIL/USDT:USDT': 30,
            'WIF/USDT:USDT': 30,
            'WLD/USDT:USDT': 30,
            'ZRO/USDT:USDT': 20,
        }
        
        # 仓位配置 - 使用100%资金
        self.position_percentage = 1.0
        
        # 持仓和挂单缓存
        self.positions_cache: Dict[str, Dict] = {}
        self.open_orders_cache: Dict[str, List] = {}
        self.last_sync_time: float = 0
        self.sync_interval: int = 60  # 60秒同步一次状态
        
        # 市场信息缓存
        self.markets_info: Dict[str, Dict] = {}
        
        # 交易统计
        self.stats = TradingStats()
        
        # 记录上次持仓状态，用于判断是否已平仓
        self.last_position_state: Dict[str, str] = {}  # symbol -> 'long'/'short'/'none'
        
        # 初始化交易所
        self._setup_exchange()
        
        # 加载市场信息
        self._load_markets()
        
        # 首次同步状态
        self.sync_all_status()
        
        # 处理启动前已有的持仓和挂单
        self.handle_existing_positions_and_orders()
    
    def _setup_exchange(self):
        """设置交易所配置"""
        try:
            # 检查连接
            self.exchange.check_required_credentials()
            logger.info("✅ API连接验证成功")
            
            # 同步交易所时间
            self.sync_exchange_time()
            
            # 预加载市场数据（容错）：仅加载swap，失败则记录并继续，后续使用安全回退
            try:
                self.exchange.load_markets({'type': 'swap'})
                logger.info("✅ 预加载市场数据完成 (swap)")
            except Exception as e:
                logger.warning(f"⚠️ 预加载市场数据失败，将使用安全回退: {e}")
            
            # 按交易对设置杠杆（OKX参数为 mgnMode 而非 marginMode）
            for symbol in self.symbols:
                try:
                    lev = self.symbol_leverage.get(symbol, 20)
                    self.exchange.set_leverage(lev, symbol, {'mgnMode': 'cross'})
                    logger.info(f"✅ 设置{symbol}杠杆为{lev}倍")
                except Exception as e:
                    logger.warning(f"⚠️ 设置{symbol}杠杆失败（可能已设置）: {e}")
            
            # 尝试设置合约模式（如果有持仓会失败，但不影响运行）
            try:
                self.exchange.set_position_mode(True)  # 双向持仓（多空分开）
                logger.info("✅ 设置为双向持仓模式（多空分开）")
            except Exception as e:
                logger.warning(f"⚠️ 设置持仓模式失败（当前可能有持仓，跳过设置）")
                logger.info("ℹ️ 程序将继续运行，使用当前持仓模式")
            
        except Exception as e:
            logger.error(f"❌ 交易所设置失败: {e}")
            raise
    
    def _load_markets(self):
        """加载市场信息（获取最小下单量等限制）"""
        try:
            logger.info("🔄 加载市场信息...")
            try:
                markets = self.exchange.load_markets({'type': 'swap'})
            except Exception as e:
                logger.warning(f"⚠️ 加载市场信息失败，使用回退参数: {e}")
                markets = {}
            
            for symbol in self.symbols:
                if symbol in markets:
                    market = markets[symbol]
                    # 优先从limits读取，其次从info中的细粒度定义读取
                    min_amount = float((market.get('limits') or {}).get('amount', {}).get('min') or 0) or \
                                 float((market.get('info') or {}).get('minSz') or 0) or \
                                 float((market.get('info') or {}).get('lotSz') or 0) or 0.0
                    lot_size = float((market.get('info') or {}).get('lotSz') or 0) or 0.0
                    self.markets_info[symbol] = {
                        'min_amount': min_amount if min_amount > 0 else 0.000001,
                        'min_cost': float((market.get('limits') or {}).get('cost', {}).get('min') or 0) or 0.0,
                        'amount_precision': market['precision']['amount'],
                        'price_precision': market['precision']['price'],
                        'lot_size': lot_size if lot_size > 0 else None,
                    }
                    logger.info(f"📊 {symbol} - 最小数量:{self.markets_info[symbol]['min_amount']:.8f}, 最小金额:{self.markets_info[symbol]['min_cost']:.4f}U")
            
            logger.info("✅ 市场信息加载完成")
            
        except Exception as e:
            logger.error(f"❌ 加载市场信息失败: {e}")
            # 小币种设置更宽松的默认值
            for symbol in self.symbols:
                self.markets_info[symbol] = {
                    'min_amount': 0.000001,
                    'min_cost': 0.1,  # 小币种最小0.1U（仅提示，不做强校验）
                    'amount_precision': 8,
                    'price_precision': 4,
                    'lot_size': None,
                }
    
    def sync_exchange_time(self):
        """同步交易所时间 - 使用中国时区"""
        try:
            server_time = self.exchange.fetch_time()
            local_time = int(time.time() * 1000)
            time_diff = server_time - local_time
            
            # 转换为中国时区
            china_tz = pytz.timezone('Asia/Shanghai')
            server_dt = datetime.datetime.fromtimestamp(server_time / 1000, tz=china_tz)
            local_dt = datetime.datetime.fromtimestamp(local_time / 1000, tz=china_tz)
            
            logger.info(f"🕐 交易所时间: {server_dt.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
            logger.info(f"🕐 本地时间: {local_dt.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
            logger.info(f"⏱️ 时间差: {time_diff}ms")
            
            if abs(time_diff) > 5000:
                logger.warning(f"⚠️ 时间差较大: {time_diff}ms，可能影响交易")
            
            return time_diff
            
        except Exception as e:
            logger.error(f"❌ 同步时间失败: {e}")
            return 0
    
    def get_open_orders(self, symbol: str) -> List[Dict]:
        """获取未成交订单"""
        try:
            orders = self.exchange.fetch_open_orders(symbol, self.okx_params)
            return orders
        except Exception as e:
            logger.error(f"❌ 获取{symbol}挂单失败: {e}")
            return []
    
    def cancel_all_orders(self, symbol: str) -> bool:
        """取消所有未成交订单"""
        try:
            orders = self.get_open_orders(symbol)
            if not orders:
                return True
            
            for order in orders:
                try:
                    self.exchange.cancel_order(order['id'], symbol)
                    logger.info(f"✅ 取消订单: {symbol} {order['id']}")
                except Exception as e:
                    logger.error(f"❌ 取消订单失败: {order['id']} - {e}")
            
            return True
        except Exception as e:
            logger.error(f"❌ 批量取消订单失败: {e}")
            return False
    
    def sync_all_status(self):
        """同步所有状态（持仓和挂单）"""
        try:
            logger.info("🔄 开始同步状态...")
            
            # 同步时间
            self.sync_exchange_time()
            
            # 同步所有交易对的持仓和挂单
            has_positions = False
            has_orders = False
            
            for symbol in self.symbols:
                # 同步持仓
                position = self.get_position(symbol, force_refresh=True)
                self.positions_cache[symbol] = position
                
                # 记录持仓状态
                if position['size'] > 0:
                    self.last_position_state[symbol] = position['side']
                    has_positions = True
                else:
                    self.last_position_state[symbol] = 'none'
                
                # 同步挂单
                orders = self.get_open_orders(symbol)
                self.open_orders_cache[symbol] = orders
                
                # 输出状态
                if position['size'] > 0:
                    logger.info(f"📊 {symbol} 持仓: {position['side']} {position['size']:.6f} @{position['entry_price']:.2f} PNL:{position['unrealized_pnl']:.2f}U 杠杆:{position['leverage']}x")
                
                if orders:
                    has_orders = True
                    logger.info(f"📋 {symbol} 挂单数量: {len(orders)}")
                    for order in orders:
                        logger.info(f"   └─ {order['side']} {order['amount']:.6f} @{order.get('price', 'market')}")
            
            if not has_positions:
                logger.info("ℹ️ 当前无持仓")
            
            if not has_orders:
                logger.info("ℹ️ 当前无挂单")
            
            self.last_sync_time = time.time()
            logger.info("✅ 状态同步完成")
            
        except Exception as e:
            logger.error(f"❌ 同步状态失败: {e}")
    
    def handle_existing_positions_and_orders(self):
        """处理程序启动时已有的持仓和挂单"""
        logger.info("=" * 70)
        logger.info("🔍 检查启动前的持仓和挂单状态...")
        logger.info("=" * 70)
        
        has_positions = False
        has_orders = False
        
        # 检查余额
        balance = self.get_account_balance()
        logger.info(f"💰 当前可用余额: {balance:.4f} USDT")
        logger.info(f"💡 小币种交易：即使只有0.1U也可以下单")
        
        for symbol in self.symbols:
            # 检查持仓
            position = self.get_position(symbol, force_refresh=True)
            if position['size'] > 0:
                has_positions = True
                logger.warning(f"⚠️ 检测到{symbol}已有持仓: {position['side']} {position['size']:.6f} @{position['entry_price']:.4f} PNL:{position['unrealized_pnl']:.2f}U")
                # 记录已有持仓状态
                self.last_position_state[symbol] = position['side']
            
            # 检查挂单
            orders = self.get_open_orders(symbol)
            if orders:
                has_orders = True
                logger.warning(f"⚠️ 检测到{symbol}有{len(orders)}个未成交订单")
                for order in orders:
                    logger.info(f"   └─ {order['side']} {order['amount']:.6f} @{order.get('price', 'market')} ID:{order['id']}")
        
        if has_positions or has_orders:
            logger.info("=" * 70)
            logger.info("❓ 程序启动时检测到已有持仓或挂单")
            logger.info("💡 策略说明:")
            logger.info("   1. 已有持仓: 程序会根据MACD信号管理，出现反向信号时平仓")
            logger.info("   2. 已有挂单: 程序会在下次交易前自动取消")
            logger.info("   3. 程序会继续运行并根据信号执行交易")
            logger.info("=" * 70)
            logger.info("⚠️ 如果需要立即平仓所有持仓，请手动操作或重启程序前先手动平仓")
            logger.info("=" * 70)
        else:
            logger.info("✅ 启动前无持仓和挂单，可以正常运行")
            logger.info("=" * 70)
    
    def display_current_positions(self):
        """显示当前所有持仓状态"""
        logger.info("")
        logger.info("=" * 70)
        logger.info("📊 当前持仓状态")
        logger.info("=" * 70)
        
        has_positions = False
        total_pnl = 0.0
        
        for symbol in self.symbols:
            position = self.get_position(symbol, force_refresh=False)
            if position['size'] > 0:
                has_positions = True
                pnl = position['unrealized_pnl']
                total_pnl += pnl
                pnl_emoji = "📈" if pnl > 0 else "📉" if pnl < 0 else "➖"
                logger.info(f"{pnl_emoji} {symbol}: {position['side'].upper()} | 数量:{position['size']:.6f} | 入场价:{position['entry_price']:.2f} | 盈亏:{pnl:.2f}U | 杠杆:{position['leverage']}x")
        
        if has_positions:
            total_emoji = "💰" if total_pnl > 0 else "💸" if total_pnl < 0 else "➖"
            logger.info("-" * 70)
            logger.info(f"{total_emoji} 总浮动盈亏: {total_pnl:.2f} USDT")
        else:
            logger.info("ℹ️ 当前无持仓")
        
        logger.info("=" * 70)
        logger.info("")
    
    def check_sync_needed(self):
        """检查是否需要同步状态"""
        current_time = time.time()
        if current_time - self.last_sync_time >= self.sync_interval:
            self.sync_all_status()
    
    def get_account_balance(self) -> float:
        """获取账户余额"""
        try:
            balance = self.exchange.fetch_balance({'type': 'swap'})
            free_balance = float(balance['USDT']['free'])
            total_balance = float(balance['USDT']['total'])
            used_balance = float(balance['USDT']['used'])
            
            logger.debug(f"💰 余额 - 可用: {free_balance:.2f} 总额: {total_balance:.2f} 占用: {used_balance:.2f}")
            return free_balance
        except Exception as e:
            logger.error(f"❌ 获取账户余额失败: {e}")
            return 0
    
    def get_klines(self, symbol: str, limit: int = 100) -> List[Dict]:
        """获取K线数据 - 15分钟周期"""
        try:
            klines = self.exchange.fetch_ohlcv(symbol, self.timeframe, limit=limit)
            # 转换为DataFrame格式并返回
            df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df.to_dict('records')
        except Exception as e:
            logger.error(f"❌ 获取{symbol}K线数据失败: {e}")
            return []
    
    def get_position(self, symbol: str, force_refresh: bool = False) -> Dict:
        """获取当前持仓（带缓存）"""
        try:
            # 如果不强制刷新且缓存存在，返回缓存
            if not force_refresh and symbol in self.positions_cache:
                return self.positions_cache[symbol]
            
            # 从交易所获取最新持仓
            positions = self.exchange.fetch_positions([symbol], self.okx_params)
            for position in positions:
                if position['symbol'] == symbol:
                    pos_data = {
                        'size': float(position.get('contracts', 0) or 0),
                        'side': position.get('side', 'none'),
                        'entry_price': float(position.get('entryPrice', 0) or 0),
                        'unrealized_pnl': float(position.get('unrealizedPnl', 0) or 0),
                        'leverage': float(position.get('leverage', 0) or 0)
                    }
                    # 更新缓存
                    self.positions_cache[symbol] = pos_data
                    return pos_data
            
            # 无持仓
            pos_data = {'size': 0, 'side': 'none', 'entry_price': 0, 'unrealized_pnl': 0, 'leverage': 0}
            self.positions_cache[symbol] = pos_data
            return pos_data
            
        except Exception as e:
            logger.error(f"❌ 获取{symbol}持仓失败: {e}")
            # 返回缓存或默认值
            if symbol in self.positions_cache:
                return self.positions_cache[symbol]
            return {'size': 0, 'side': 'none', 'entry_price': 0, 'unrealized_pnl': 0, 'leverage': 0}
    
    def has_open_orders(self, symbol: str) -> bool:
        """检查是否有未成交订单"""
        try:
            orders = self.get_open_orders(symbol)
            has_orders = len(orders) > 0
            if has_orders:
                logger.info(f"⚠️ {symbol} 存在{len(orders)}个未成交订单")
            return has_orders
        except Exception as e:
            logger.error(f"❌ 检查挂单失败: {e}")
            return False
    
    def calculate_order_amount(self, symbol: str) -> float:
        """计算下单金额（使用总余额平均分配）"""
        try:
            balance = self.get_account_balance()
            # 使用100%余额
            total_amount = balance * self.position_percentage
            
            # 平均分配到4个交易对
            allocated_amount = total_amount / len(self.symbols)
            
            # 小币种：只要有余额就下单，不设最小限制
            logger.debug(f"💵 {symbol}分配金额: {allocated_amount:.4f}U (总余额: {balance:.2f}U)")
            return allocated_amount
            
        except Exception as e:
            logger.error(f"❌ 计算{symbol}下单金额失败: {e}")
            return 0
    
    def create_order(self, symbol: str, side: str, amount: float) -> bool:
        """创建订单 - 小币种版本，支持小额交易"""
        try:
            # 检查是否有挂单
            if self.has_open_orders(symbol):
                logger.warning(f"⚠️ {symbol}存在未成交订单，先取消")
                self.cancel_all_orders(symbol)
                time.sleep(1)  # 等待订单取消
            
            # 小币种：只要金额大于0就尝试下单
            if amount <= 0:
                logger.warning(f"⚠️ {symbol}下单金额为0，跳过")
                return False
            
            # 获取市场信息
            market_info = self.markets_info.get(symbol, {})
            min_amount = market_info.get('min_amount', 0.001)
            amount_precision = market_info.get('amount_precision', 8)
            
            # 获取当前价格
            ticker = self.exchange.fetch_ticker(symbol)
            current_price = float(ticker['last'])
            
            # 计算合约数量（基于金额/价格），再按精度与最小数量修正
            contract_size = amount / current_price

            # 最小数量与步进修正
            if contract_size < min_amount:
                contract_size = min_amount

            # 使用交易所精度函数确保合法
            try:
                contract_size = float(self.exchange.amount_to_precision(symbol, contract_size))
            except Exception:
                contract_size = round(contract_size, amount_precision)

            # 防止被精度截断为0
            if contract_size <= 0:
                contract_size = max(min_amount, 10 ** (-amount_precision))
                try:
                    contract_size = float(self.exchange.amount_to_precision(symbol, contract_size))
                except Exception:
                    contract_size = round(contract_size, amount_precision)

            # 再次确保不低于最小数量
            if contract_size < min_amount:
                logger.warning(f"⚠️ {symbol}数量在精度修正后仍低于最小限制: {contract_size:.8f} < {min_amount:.8f}")
                return False
            
            logger.info(f"📝 准备下单: {symbol} {side} 金额:{amount:.4f}U 价格:{current_price:.4f} 数量:{contract_size:.8f}")
            
            # 创建市价单（OKX 对冲模式需要传 posSide）
            pos_side = 'long' if side == 'buy' else 'short'
            params = {'posSide': pos_side, 'tdMode': 'cross'}
            order = self.exchange.create_market_order(symbol, side, contract_size, params)
            
            if order['id']:
                logger.info(f"✅ 成功创建{symbol} {side}订单，金额:{amount:.4f}U，数量:{contract_size:.8f}")
                # 等待订单成交后刷新持仓
                time.sleep(2)
                self.get_position(symbol, force_refresh=True)
                return True
            else:
                logger.error(f"❌ 创建{symbol} {side}订单失败")
                return False
                
        except Exception as e:
            logger.error(f"❌ 创建{symbol} {side}订单异常: {e}")
            return False
    
    def close_position(self, symbol: str, open_reverse: bool = False) -> bool:
        """平仓；如 open_reverse=True，平仓后立即反向开仓"""
        try:
            # 先取消所有挂单
            if self.has_open_orders(symbol):
                logger.info(f"🔄 平仓前先取消{symbol}的挂单")
                self.cancel_all_orders(symbol)
                time.sleep(1)
            
            # 刷新持仓
            position = self.get_position(symbol, force_refresh=True)
            
            if position['size'] == 0:
                logger.info(f"ℹ️ {symbol}无持仓，无需平仓")
                return True
            
            # 记录平仓前的盈亏
            pnl = position.get('unrealized_pnl', 0)
            position_side = position.get('side', 'unknown')
            
            # 获取合约数量
            size = float(position.get('size', 0) or 0)
            
            # 反向平仓：多头平仓用sell，空头平仓用buy
            side = 'sell' if position.get('side') == 'long' else 'buy'
            
            logger.info(f"📝 准备平仓: {symbol} {side} 数量:{size:.6f} 预计盈亏:{pnl:.2f}U")
            
            # 使用reduceOnly参数以确保只是平仓；OKX 需指定当前持仓方向的 posSide
            order = self.exchange.create_market_order(symbol, side, size, {'reduceOnly': True, 'posSide': position_side, 'tdMode': 'cross'})
            
            if order['id']:
                logger.info(f"✅ 成功平仓{symbol}，方向: {side}，数量: {size:.6f}，盈亏: {pnl:.2f}U")
                
                # 记录交易统计
                self.stats.add_trade(symbol, position_side, pnl)
                
                # 等待平仓成交后刷新持仓
                time.sleep(2)
                self.get_position(symbol, force_refresh=True)
                
                # 更新上次持仓状态
                self.last_position_state[symbol] = 'none'

                # 平仓后根据需要反向开仓
                if open_reverse:
                    reverse_side = 'sell' if position_side == 'long' else 'buy'
                    amount = self.calculate_order_amount(symbol)
                    if amount > 0:
                        if self.create_order(symbol, reverse_side, amount):
                            logger.info(f"🔁 平仓后已反向开仓 {symbol} -> {reverse_side}")
                
                return True
            else:
                logger.error(f"❌ 平仓{symbol}失败")
                return False
                
        except Exception as e:
            logger.error(f"❌ 平仓{symbol}失败: {e}")
            return False
    
    def calculate_macd(self, prices: List[float]) -> Dict[str, float]:
        """计算MACD指标"""
        # 转换为numpy数组
        close_array = np.array(prices)
        
        # 计算EMA
        ema_fast = pd.Series(close_array).ewm(span=self.fast_period, adjust=False).mean().values
        ema_slow = pd.Series(close_array).ewm(span=self.slow_period, adjust=False).mean().values
        
        # 计算MACD线
        macd_line = ema_fast - ema_slow
        
        # 计算信号线
        signal_line = pd.Series(macd_line).ewm(span=self.signal_period, adjust=False).mean().values
        
        # 计算柱状图
        histogram = macd_line - signal_line
        
        # 返回最新的MACD值
        return {
            'macd': macd_line[-1],
            'signal': signal_line[-1],
            'histogram': histogram[-1],
            'macd_line': macd_line,
            'signal_line': signal_line
        }
    
    def analyze_symbol(self, symbol: str) -> Dict[str, str]:
        """分析单个交易对"""
        try:
            # 获取K线数据
            klines = self.get_klines(symbol, 100)
            if not klines:
                return {'signal': 'hold', 'reason': '数据获取失败'}
            
            # 提取收盘价（包含最新正在形成的K线）
            closes = [kline['close'] for kline in klines]

            if len(closes) < 2:
                return {'signal': 'hold', 'reason': '数据不足'}

            # 使用实时K线：当前与前一根（不等待收盘）
            macd_current = self.calculate_macd(closes)
            macd_prev = self.calculate_macd(closes[:-1])
            
            # 获取持仓（使用缓存，避免频繁请求）
            position = self.get_position(symbol, force_refresh=False)
            
            # 使用实时K线进行交叉与柱状图颜色变化判断
            prev_macd = macd_prev['macd']
            prev_signal = macd_prev['signal']
            prev_hist = macd_prev['histogram']
            current_macd = macd_current['macd']
            current_signal = macd_current['signal']
            current_hist = macd_current['histogram']
            
            logger.debug(f"📊 {symbol} MACD(实时) - 当前: MACD={current_macd:.6f}, Signal={current_signal:.6f}, Hist={current_hist:.6f}")
            
            # 生成交易信号
            if position['size'] == 0:  # 无持仓
                # 金叉信号：快线上穿慢线 或 柱状图由绿转红（负到正）
                if (prev_macd <= prev_signal and current_macd > current_signal) or (prev_hist <= 0 and current_hist > 0):
                    return {'signal': 'buy', 'reason': 'MACD金叉（快线上穿慢线）'}
                
                # 死叉信号：快线下穿慢线 或 柱状图由红转绿（正到负）
                elif (prev_macd >= prev_signal and current_macd < current_signal) or (prev_hist >= 0 and current_hist < 0):
                    return {'signal': 'sell', 'reason': 'MACD死叉（快线下穿慢线）'}
                
                else:
                    return {'signal': 'hold', 'reason': '等待交叉信号'}
            
            else:  # 有持仓
                current_position_side = position['side']
                
                # 检查持仓方向是否与上次记录一致，如果一致说明没有平仓过
                last_side = self.last_position_state.get(symbol, 'none')
                
                if current_position_side == 'long':
                    # 多头平仓：快线下穿慢线 或 柱状图转负
                    if (prev_macd >= prev_signal and current_macd < current_signal) or (current_hist < 0):
                        return {'signal': 'close', 'reason': '多头平仓（死叉）'}
                    else:
                        return {'signal': 'hold', 'reason': '持有多头'}
                
                else:  # short
                    # 空头平仓：快线上穿慢线 或 柱状图转正
                    if (prev_macd <= prev_signal and current_macd > current_signal) or (current_hist > 0):
                        return {'signal': 'close', 'reason': '空头平仓（金叉）'}
                    else:
                        return {'signal': 'hold', 'reason': '持有空头'}
                        
        except Exception as e:
            logger.error(f"❌ 分析{symbol}失败: {e}")
            return {'signal': 'hold', 'reason': f'分析异常: {e}'}
    
    def execute_strategy(self):
        """执行策略"""
        logger.info("=" * 70)
        logger.info("🚀 开始执行MACD策略 (分币种杠杆，15分钟周期)")
        logger.info("=" * 70)
        
        try:
            # 检查是否需要同步状态
            self.check_sync_needed()
            
            # 显示当前余额
            balance = self.get_account_balance()
            logger.info(f"💰 当前账户余额: {balance:.2f} USDT")
            
            # 显示交易统计
            logger.info(self.stats.get_summary())
            
            # 显示当前持仓状态
            self.display_current_positions()
            
            logger.info("🔍 分析交易信号...")
            logger.info("-" * 70)
            
            # 分析所有交易对
            signals = {}
            for symbol in self.symbols:
                signals[symbol] = self.analyze_symbol(symbol)
                position = self.get_position(symbol, force_refresh=False)
                open_orders = self.get_open_orders(symbol)
                
                status_line = f"📊 {symbol}: 信号={signals[symbol]['signal']}, 原因={signals[symbol]['reason']}"
                if open_orders:
                    status_line += f", 挂单={len(open_orders)}个"
                
                logger.info(status_line)
            
            logger.info("-" * 70)
            logger.info("⚡ 执行交易操作...")
            logger.info("")
            
            # 执行交易
            for symbol, signal_info in signals.items():
                signal = signal_info['signal']
                reason = signal_info['reason']
                
                # 获取当前持仓
                current_position = self.get_position(symbol, force_refresh=False)
                
                if signal == 'buy':
                    # 检查是否已经是多头持仓，如果是则不重复开仓
                    if current_position['size'] > 0 and current_position['side'] == 'long':
                        logger.info(f"ℹ️ {symbol}已有多头持仓，跳过重复开仓")
                        continue
                    
                    # 做多：金叉信号
                    amount = self.calculate_order_amount(symbol)
                    if amount > 0:
                        if self.create_order(symbol, 'buy', amount):
                            logger.info(f"🚀 开多{symbol}成功 - {reason}")
                            self.last_position_state[symbol] = 'long'
                
                elif signal == 'sell':
                    # 检查是否已经是空头持仓，如果是则不重复开仓
                    if current_position['size'] > 0 and current_position['side'] == 'short':
                        logger.info(f"ℹ️ {symbol}已有空头持仓，跳过重复开仓")
                        continue
                    
                    # 做空：死叉信号
                    amount = self.calculate_order_amount(symbol)
                    if amount > 0:
                        if self.create_order(symbol, 'sell', amount):
                            logger.info(f"📉 开空{symbol}成功 - {reason}")
                            self.last_position_state[symbol] = 'short'
                
                elif signal == 'close':
                    # 平仓并反手开仓
                    if self.close_position(symbol, open_reverse=True):
                        logger.info(f"✅ 平仓并反手开仓 {symbol} 成功 - {reason}")
            
            logger.info("=" * 70)
                        
        except Exception as e:
            logger.error(f"❌ 执行策略失败: {e}")
    
    def run_continuous(self, interval: int = 30):
        """连续运行策略"""
        logger.info("=" * 70)
        logger.info("🚀 MACD策略启动 - RAILWAY平台版 (小币种)")
        logger.info("=" * 70)
        logger.info(f"📈 MACD参数: 快线={self.fast_period}, 慢线={self.slow_period}, 信号线={self.signal_period}")
        logger.info(f"📊 K线周期: {self.timeframe} (15分钟)")
        lev_desc = ', '.join([f"{s.split('/')[0]}={self.symbol_leverage.get(s, 20)}x" for s in self.symbols])
        logger.info(f"💪 杠杆倍数: {lev_desc}")
        logger.info(f"⏰ 运行间隔: {interval}秒 ({interval/60:.1f}分钟)")
        logger.info(f"🔄 状态同步: 每{self.sync_interval}秒")
        logger.info(f"📊 监控币种: {', '.join(self.symbols)}")
        logger.info(f"💡 小币种特性: 支持0.1U起的小额交易")
        logger.info(self.stats.get_summary())
        logger.info("=" * 70)
        
        # 对齐扫描参数（用于15分钟图：在每根K线收盘前1分钟开始扫描）
        align_to_15m = os.environ.get('ALIGN_TO_15M', 'true').strip().lower() in ('1', 'true', 'yes')
        try:
            scan_window_sec = int(os.environ.get('SCAN_WINDOW_SEC', '60'))
            scan_step_sec = int(os.environ.get('SCAN_STEP_SEC', '3'))
        except Exception:
            scan_window_sec = 60
            scan_step_sec = 3

        china_tz = pytz.timezone('Asia/Shanghai')

        def floor_to_15m(dt: datetime.datetime) -> datetime.datetime:
            minute = (dt.minute // 15) * 15
            return dt.replace(minute=minute, second=0, microsecond=0)

        while True:
            try:
                if align_to_15m:
                    now = datetime.datetime.now(china_tz)
                    base = floor_to_15m(now)
                    # 窗口在每个15分钟周期的第14分钟开始
                    window_start = base + datetime.timedelta(minutes=14)
                    if now >= base + datetime.timedelta(minutes=15):
                        # 已过当前周期，滚动到下一个周期
                        base = base + datetime.timedelta(minutes=15)
                        window_start = base + datetime.timedelta(minutes=14)
                    if now < window_start:
                        sleep_sec = max(0.0, (window_start - now).total_seconds())
                        logger.info(f"⏲️ 将在对齐窗口开始扫描: {window_start.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)，等待{int(sleep_sec)}秒...")
                        time.sleep(sleep_sec)

                    # 窗口内连续扫描
                    window_end = window_start + datetime.timedelta(seconds=scan_window_sec)
                    logger.info(f"🔎 已进入窗口 [{window_start.strftime('%H:%M:%S')} ~ {window_end.strftime('%H:%M:%S')}]，步长{scan_step_sec}s")
                    while datetime.datetime.now(china_tz) < window_end:
                        self.execute_strategy()
                        time.sleep(max(1, scan_step_sec))

                    # 窗口结束后，等待到下一个周期窗口
                    next_base = base + datetime.timedelta(minutes=15)
                    next_window_start = next_base + datetime.timedelta(minutes=14)
                    wait_sec = max(0.0, (next_window_start - datetime.datetime.now(china_tz)).total_seconds())
                    logger.info(f"⏳ 窗口结束，下一窗口 {next_window_start.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)，等待{int(wait_sec)}秒...")
                    time.sleep(wait_sec)
                else:
                    start_ts = time.time()
                    self.execute_strategy()
                    next_run_ts = start_ts + interval
                    next_run_dt = datetime.datetime.fromtimestamp(next_run_ts, tz=china_tz)
                    logger.info(f"⏳ 等待下次执行，间隔{interval}秒 ({interval/60:.1f}分钟)，预计: {next_run_dt.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
                    logger.info("")
                    time.sleep(interval)
                
            except KeyboardInterrupt:
                logger.info("⛔ 用户中断，策略停止")
                break
            except Exception as e:
                logger.error(f"❌ 策略运行异常: {e}")
                logger.info("🔄 60秒后重试...")
                time.sleep(60)

def main():
    """主函数"""
    logger.info("=" * 70)
    logger.info("🎯 MACD策略程序启动中...")
    logger.info("=" * 70)
    
    # 从环境变量获取API配置
    okx_api_key = os.environ.get('OKX_API_KEY', '')
    okx_secret_key = os.environ.get('OKX_SECRET_KEY', '')
    okx_passphrase = os.environ.get('OKX_PASSPHRASE', '')
    
    # 检查环境变量是否设置
    missing_vars = []
    if not okx_api_key:
        missing_vars.append('OKX_API_KEY')
    if not okx_secret_key:
        missing_vars.append('OKX_SECRET_KEY')
    if not okx_passphrase:
        missing_vars.append('OKX_PASSPHRASE')
    
    if missing_vars:
        logger.error(f"❌ 缺少环境变量: {', '.join(missing_vars)}")
        logger.error("💡 请在RAILWALL平台上设置这些环境变量")
        return
    
    logger.info("✅ 环境变量检查通过")
    
    # 创建策略实例
    try:
        strategy = MACDStrategy(
            api_key=okx_api_key,
            secret_key=okx_secret_key,
            passphrase=okx_passphrase
        )
        
        logger.info("✅ 策略初始化成功")
        
        # 运行策略（扫描间隔可通过环境变量 SCAN_INTERVAL 覆盖，单位秒，默认30s）
        try:
            scan_interval_env = os.environ.get('SCAN_INTERVAL', '').strip()
            scan_interval = int(scan_interval_env) if scan_interval_env else 30
            if scan_interval <= 0:
                scan_interval = 30
        except Exception:
            scan_interval = 30
        logger.info(f"🛠 扫描间隔设置: {scan_interval} 秒（可用环境变量 SCAN_INTERVAL 覆盖）")
        strategy.run_continuous(interval=scan_interval)
        
    except Exception as e:
        logger.error(f"❌ 策略初始化或运行失败: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main()
