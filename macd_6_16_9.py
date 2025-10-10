#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MACD策略实现 - RAILWAY平台版本
25倍杠杆，无限制交易，带挂单识别和状态同步
增加胜率统计和盈亏显示
"""
import time
import logging
import datetime
import os
import json
from typing import Dict, Any, List, Optional, Literal, cast
import pytz

import ccxt
import pandas as pd
import numpy as np
import math

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

        # 将统一交易对转为OKX instId，例如 FIL/USDT:USDT -> FIL-USDT-SWAP
        def _symbol_to_inst_id(sym: str) -> str:
            try:
                base = sym.split('/')[0]
                return f"{base}-USDT-SWAP"
            except Exception:
                return ''
        self.symbol_to_inst_id = _symbol_to_inst_id
        
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
        self.fast_period = 10
        self.slow_period = 40
        self.signal_period = 15
        
        # 杠杆配置 - 分币种设置
        self.symbol_leverage: Dict[str, int] = {
            'FIL/USDT:USDT': 30,
            'WIF/USDT:USDT': 25,
            'WLD/USDT:USDT': 30,
            'ZRO/USDT:USDT': 20,
        }
        
        # 分币种参数（MACD/ATR/ADX/SL/TP/反手）
        self.per_symbol_params: Dict[str, Dict[str, Any]] = {
            'FIL/USDT:USDT': {'macd': (10, 40, 15), 'atr_period': 14, 'adx_period': 14, 'adx_min_trend': 25, 'sl_n': 2.0, 'tp_m': 3.5, 'allow_reverse': True},
            'ZRO/USDT:USDT': {'macd': (9, 35, 12), 'atr_period': 14, 'adx_period': 10, 'adx_min_trend': 30, 'sl_n': 2.2, 'tp_m': 3.0, 'allow_reverse': False},
            'WIF/USDT:USDT': {'macd': (9, 30, 12), 'atr_period': 14, 'adx_period': 10, 'adx_min_trend': 30, 'sl_n': 2.5, 'tp_m': 2.8, 'allow_reverse': False},
            'WLD/USDT:USDT': {'macd': (10, 40, 15), 'atr_period': 14, 'adx_period': 14, 'adx_min_trend': 25, 'sl_n': 2.0, 'tp_m': 3.5, 'allow_reverse': True},
        }
        
        # 仓位配置 - 使用100%资金
        self.position_percentage = 1.0
        
        # 持仓和挂单缓存
        self.positions_cache: Dict[str, Dict[str, Any]] = {}
        self.open_orders_cache: Dict[str, List[Dict[str, Any]]] = {}
        self.last_sync_time: float = 0
        self.sync_interval: int = 60  # 60秒同步一次状态
        
        # 市场信息缓存
        self.markets_info: Dict[str, Dict[str, Any]] = {}
        # API 速率限制（节流器）：默认最小间隔 0.2s，可用 OKX_API_MIN_INTERVAL 覆盖
        self._last_api_ts: float = 0.0
        try:
            self._min_api_interval: float = float((os.environ.get('OKX_API_MIN_INTERVAL') or '0.2').strip())
        except Exception:
            self._min_api_interval = 0.2
        
        # 交易统计
        self.stats = TradingStats()
        
        # ATR 止盈止损参数（环境变量可覆盖）：N=止损倍数，M=止盈倍数
        try:
            self.atr_sl_n = float((os.environ.get('ATR_SL_N') or '2.0').strip())
        except Exception:
            self.atr_sl_n = 2.0
        try:
            self.atr_tp_m = float((os.environ.get('ATR_TP_M') or '3.0').strip())
        except Exception:
            self.atr_tp_m = 3.0
        # SL/TP 状态缓存：symbol -> {'sl': float, 'tp': float, 'side': 1/-1, 'entry': float}
        self.sl_tp_state: Dict[str, Dict[str, float]] = {}
        # 交易所侧TP/SL已挂标记：symbol -> bool
        self.okx_tp_sl_placed: Dict[str, bool] = {}
        # 每币种参数配置（硬编码）
        self.symbol_cfg: Dict[str, Dict[str, float | str]] = {
            "ZRO/USDT:USDT": {"period": 14, "n": 1.8, "m": 2.6, "trigger_pct": 0.008, "trail_pct": 0.005, "update_basis": "high"},
            "WIF/USDT:USDT": {"period": 20, "n": 2.5, "m": 3.0, "trigger_pct": 0.012, "trail_pct": 0.008, "update_basis": "high"},
            "WLD/USDT:USDT": {"period": 20, "n": 2.0, "m": 3.0, "trigger_pct": 0.010, "trail_pct": 0.006, "update_basis": "close"},
            "FIL/USDT:USDT": {"period": 20, "n": 2.2, "m": 3.5, "trigger_pct": 0.010, "trail_pct": 0.006, "update_basis": "high"},
        }
        # 跟踪峰值/谷值（用于动态止损）
        self.trailing_peak: Dict[str, float] = {}   # long使用：记录最高价
        self.trailing_trough: Dict[str, float] = {} # short使用：记录最低价
        
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
            # 强制设定 OKX API 版本，避免 ccxt 内部 URL 拼接出现 None + str
            try:
                self.exchange.version = 'v5'
            except Exception:
                pass
            # 统一默认类型与结算币种，减少内部推断
            try:
                opts = self.exchange.options or {}
                opts.update({'defaultType': 'swap', 'defaultSettle': 'USDT', 'version': 'v5'})
                self.exchange.options = opts
            except Exception:
                pass
            logger.info("✅ API连接验证成功")
            
            # 同步交易所时间
            self.sync_exchange_time()
            
            # 预加载市场数据（容错）：仅加载swap，失败则记录并继续，后续使用安全回退
            try:
                self.exchange.load_markets(True, {'type': 'swap'})
                logger.info("✅ 预加载市场数据完成 (swap)")
            except Exception as e:
                logger.warning(f"⚠️ 预加载市场数据失败，将使用安全回退: {e}")
            
            # 按交易对设置杠杆（使用OKX原生接口，避免统一封装问题）
            for symbol in self.symbols:
                try:
                    lev = self.symbol_leverage.get(symbol, 20)
                    inst_id = self.symbol_to_inst_id(symbol)
                    # 分别设置多空两边的杠杆
                    try:
                        self.exchange.privatePostAccountSetLeverage({'instId': inst_id, 'lever': str(lev), 'mgnMode': 'cross', 'posSide': 'long'})
                    except Exception:
                        pass
                    try:
                        self.exchange.privatePostAccountSetLeverage({'instId': inst_id, 'lever': str(lev), 'mgnMode': 'cross', 'posSide': 'short'})
                    except Exception:
                        pass
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
            # 使用 OKX v5 原生接口获取合约规格，避免统一封装
            resp = self.exchange.publicGetPublicInstruments({'instType': 'SWAP'})
            data = resp.get('data') if isinstance(resp, dict) else resp
            # 建立 instId -> 规格 映射
            spec_map = {}
            for it in (data or []):
                if it.get('settleCcy') == 'USDT':  # 仅 USDT 结算
                    spec_map[it.get('instId')] = it
            for symbol in self.symbols:
                inst_id = self.symbol_to_inst_id(symbol)
                it = spec_map.get(inst_id, {})
                # 解析规格
                min_sz = float(it.get('minSz') or 0) or 0.000001
                lot_sz = float(it.get('lotSz') or 0) or None
                tick_sz = float(it.get('tickSz') or 0) or 0.0001
                amt_prec = len(str(lot_sz).split('.')[-1]) if lot_sz and '.' in str(lot_sz) else 8
                px_prec = len(str(tick_sz).split('.')[-1]) if '.' in str(tick_sz) else 4
                self.markets_info[symbol] = {
                    'min_amount': min_sz,
                    'min_cost': 0.0,
                    'amount_precision': amt_prec,
                    'price_precision': px_prec,
                    'lot_size': lot_sz,
                }
                logger.info(f"📊 {symbol} - 最小数量:{min_sz:.8f} 步进:{(lot_sz or 0):.8f} Tick:{tick_sz:.8f}")
            logger.info("✅ 市场信息加载完成")
        except Exception as e:
            logger.error(f"❌ 加载市场信息失败: {e}")
            # 小币种设置更宽松的默认值
            for symbol in self.symbols:
                self.markets_info[symbol] = {
                    'min_amount': 0.000001,
                    'min_cost': 0.1,
                    'amount_precision': 8,
                    'price_precision': 4,
                    'lot_size': None,
                }
    
    def sync_exchange_time(self):
        """同步交易所时间 - 使用中国时区"""
        try:
            server_time = int(self.exchange.fetch_time() or 0)
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
    
    def get_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """获取未成交订单（OKX原生接口，避免markets依赖）"""
        try:
            inst_id = self.symbol_to_inst_id(symbol)
            resp = self.exchange.privateGetTradeOrdersPending({'instType': 'SWAP', 'instId': inst_id})
            data = resp.get('data') if isinstance(resp, dict) else resp
            results = []
            for o in (data or []):
                results.append({
                    'id': o.get('ordId') or o.get('clOrdId'),
                    'side': 'buy' if o.get('side') == 'buy' else 'sell',
                    'amount': float(o.get('sz') or 0),
                    'price': float(o.get('px') or 0) if o.get('px') else None,
                })
            return results
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

    def cancel_symbol_tp_sl(self, symbol: str) -> bool:
        """撤销该交易对在OKX侧已挂的TP/SL（OCO）条件单"""
        try:
            inst_id = self.symbol_to_inst_id(symbol)
            if not inst_id:
                return True
            # 查询待触发的条件单（OCO）
            resp = self.exchange.privateGetTradeOrdersAlgoPending({'instType': 'SWAP', 'instId': inst_id})
            data = resp.get('data') if isinstance(resp, dict) else resp
            algo_ids = []
            for it in (data or []):
                try:
                    if (it.get('ordType') or '').lower() == 'oco':
                        aid = it.get('algoId') or it.get('algoID') or it.get('id')
                        if aid:
                            algo_ids.append({'algoId': str(aid), 'instId': inst_id})
                except Exception:
                    continue
            if not algo_ids:
                return True
            # 撤销OCO（OKX规范是传对象数组；若失败，降级为兼容形式）
            try:
                self.exchange.privatePostTradeCancelAlgos({'algoIds': algo_ids})
            except Exception:
                self.exchange.privatePostTradeCancelAlgos({'algoIds': [x['algoId'] for x in algo_ids], 'instId': inst_id})
            logger.info(f"✅ 撤销 {symbol} 已挂 OCO 条件单数量: {len(algo_ids)}")
            return True
        except Exception as e:
            logger.warning(f"⚠️ 撤销 {symbol} 条件单失败: {e}")
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
                # 启动时为已有持仓补挂交易所侧TP/SL
                try:
                    kl = self.get_klines(symbol, 50)
                    atr_p = int((os.environ.get('ATR_PERIOD') or '14').strip())
                    atr_val = self.calculate_atr(kl, atr_p) if kl else 0.0
                    entry = float(position.get('entry_price', 0) or 0)
                    if atr_val > 0 and entry > 0:
                        okx_ok = self.place_okx_tp_sl(symbol, entry, position.get('side', 'long'), atr_val)
                        if okx_ok:
                            logger.info(f"📌 已为已有持仓补挂TP/SL {symbol}")
                        else:
                            logger.warning(f"⚠️ 补挂交易所侧TP/SL失败 {symbol}")
                except Exception as _e:
                    logger.warning(f"⚠️ 补挂交易所侧TP/SL异常 {symbol}: {_e}")
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
        """获取账户余额（OKX原生接口）"""
        try:
            resp = self.exchange.privateGetAccountBalance({})
            data = resp.get('data') if isinstance(resp, dict) else resp
            # data 结构: [{ details: [{ccy:'USDT', cashBal:'...', availBal:'...'}], ... }]
            avail = 0.0
            for acc in (data or []):
                for d in (acc.get('details') or []):
                    if d.get('ccy') == 'USDT':
                        # 优先 availBal，其次 cashBal
                        v = d.get('availBal') or d.get('cashBal') or '0'
                        try:
                            avail = float(v)
                        except Exception:
                            avail = 0.0
                        break
            return avail
        except Exception as e:
            logger.error(f"❌ 获取账户余额失败: {e}")
            return 0.0
    
    def get_klines(self, symbol: str, limit: int = 100) -> List[Dict]:
        """获取K线数据 - 5分钟周期（OKX v5 原生接口）"""
        try:
            inst_id = self.symbol_to_inst_id(symbol)
            # OKX v5: /api/v5/market/candles?instId=...&bar=15m&limit=...
            params = {'instId': inst_id, 'bar': self.timeframe, 'limit': str(limit)}
            resp = self.exchange.publicGetMarketCandles(params)
            rows = resp.get('data') if isinstance(resp, dict) else resp
            result: List[Dict] = []
            for r in (rows or []):
                # OKX返回: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
                ts = int(r[0])
                o = float(r[1]); h = float(r[2]); l = float(r[3]); c = float(r[4]); v = float(r[5])
                result.append({
                    'timestamp': pd.to_datetime(ts, unit='ms'),
                    'open': o, 'high': h, 'low': l, 'close': c, 'volume': v
                })
            # OKX通常返回从新到旧，按时间升序
            result.sort(key=lambda x: x['timestamp'])
            return result
        except Exception as e:
            logger.error(f"❌ 获取{symbol}K线数据失败: {e}")
            return []
    
    def get_position(self, symbol: str, force_refresh: bool = False) -> Dict[str, Any]:
        """获取当前持仓（带缓存）"""
        try:
            # 如果不强制刷新且缓存存在，返回缓存
            if not force_refresh and symbol in self.positions_cache:
                return self.positions_cache[symbol]
            
            # 从交易所获取最新持仓
            # 使用OKX原生接口获取持仓，避免markets依赖
            inst_id = self.symbol_to_inst_id(symbol)
            resp = self.exchange.privateGetAccountPositions({'instType': 'SWAP', 'instId': inst_id})
            data = resp.get('data') if isinstance(resp, dict) else resp
            for p in (data or []):
                if p.get('instId') == inst_id and float(p.get('pos', 0) or 0) != 0:
                    size = abs(float(p.get('pos', 0) or 0))
                    side = 'long' if p.get('posSide') == 'long' else 'short'
                    entry_price = float(p.get('avgPx', 0) or 0)
                    leverage = float(p.get('lever', 0) or 0)
                    unreal = float(p.get('upl', 0) or 0)
                    pos_data = {
                        'size': size,
                        'side': side,
                        'entry_price': entry_price,
                        'unrealized_pnl': unreal,
                        'leverage': leverage,
                    }
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
    
    def calculate_order_amount(self, symbol: str, active_count: Optional[int] = None) -> float:
        """计算下单金额（增强版：支持固定目标金额/放大因子/上下限/按信号集中分配）"""
        try:
            # 1) 固定目标名义金额（最高优先）
            target_str = os.environ.get('TARGET_NOTIONAL_USDT', '').strip()
            if target_str:
                try:
                    target = max(0.0, float(target_str))
                    logger.info(f"💵 使用固定目标名义金额: {target:.4f}U")
                    return target
                except Exception:
                    logger.warning(f"⚠️ TARGET_NOTIONAL_USDT 无效: {target_str}")

            # 2) 基于余额分配（默认平均分）
            balance = self.get_account_balance()
            if balance <= 0:
                logger.warning(f"⚠️ 余额不足，无法为 {symbol} 分配资金 (余额:{balance:.4f}U)")
                return 0.0

            alloc_mode = (os.environ.get('ALLOC_MODE', 'all') or 'all').strip().lower()
            num_symbols = max(1, len(self.symbols))
            base_divisor = num_symbols

            # 仅给有信号的币分配（需要调用处统计 active_count 并传入）
            if alloc_mode == 'signals' and active_count and active_count > 0:
                base_divisor = active_count

            allocated_amount = balance / max(1, base_divisor)

            # 3) 放大因子
            factor_str = os.environ.get('ORDER_NOTIONAL_FACTOR', '50').strip()
            try:
                factor = max(1.0, float(factor_str or '1'))
            except Exception:
                factor = 1.0
            allocated_amount *= factor

            # 4) 下限/上限
            def _to_float(env_name: str, default: float) -> float:
                try:
                    s = os.environ.get(env_name, '').strip()
                    return float(s) if s else default
                except Exception:
                    return default

            min_floor = max(0.0, _to_float('MIN_PER_SYMBOL_USDT', 0.0))
            max_cap = max(0.0, _to_float('MAX_PER_SYMBOL_USDT', 0.0))

            if min_floor > 0 and allocated_amount < min_floor:
                allocated_amount = min_floor
            if max_cap > 0 and allocated_amount > max_cap:
                allocated_amount = max_cap

            logger.info(f"💵 资金分配: 模式={alloc_mode}, 总余额={balance:.4f}U, 分母={base_divisor}, 因子={factor:.2f}, 本币目标={allocated_amount:.4f}U")
            if allocated_amount <= 0:
                logger.warning(f"⚠️ {symbol}最终分配金额为0，跳过")
                return 0.0

            return allocated_amount

        except Exception as e:
            logger.error(f"❌ 计算{symbol}下单金额失败: {e}")
            return 0.0
    
    def create_order(self, symbol: str, side: str, amount: float) -> bool:
        """创建订单 - 小币种版本，支持小额交易（OKX原生下单，避免精度与symbol转换问题）"""
        try:
            # 检查是否有挂单
            if self.has_open_orders(symbol):
                logger.warning(f"⚠️ {symbol}存在未成交订单，先取消")
                self.cancel_all_orders(symbol)
                time.sleep(1)  # 等待订单取消

            if amount <= 0:
                logger.warning(f"⚠️ {symbol}下单金额为0，跳过")
                return False

            # 获取市场信息
            market_info = self.markets_info.get(symbol, {})
            min_amount = float(market_info.get('min_amount', 0.001) or 0.001)
            amount_precision = int(market_info.get('amount_precision', 8) or 8)
            lot_sz = market_info.get('lot_size')  # 可能为 None

            # 获取当前价格（使用 OKX v5 原生接口，避免 ccxt 统一接口的 None + 'str' 问题）
            inst_id = self.symbol_to_inst_id(symbol)
            try:
                tkr = self.exchange.publicGetMarketTicker({'instId': inst_id})
                # OKX v5 返回结构 { code, data: [{ last: '...', ... }], msg }
                if isinstance(tkr, dict):
                    d = tkr.get('data') or []
                    if isinstance(d, list) and d:
                        current_price = float(d[0].get('last') or d[0].get('lastPx') or 0.0)
                    else:
                        current_price = 0.0
                else:
                    current_price = 0.0
            except Exception as _e:
                logger.error(f"❌ 获取{symbol}最新价失败({inst_id}): {_e}")
                current_price = 0.0

            if not current_price or current_price <= 0:
                logger.error(f"❌ 无法获取{symbol}有效价格，跳过下单")
                return False

            # 计算合约数量（基于金额/价格）
            contract_size = amount / current_price

            # 先确保不低于最小数量
            if contract_size < min_amount:
                contract_size = min_amount

            # 先按步进向上对齐，再按小数位四舍五入（尽量用满分配金额）
            step = None
            if lot_sz:
                try:
                    step = float(lot_sz)
                    if step and step > 0:
                        contract_size = math.ceil(contract_size / step) * step
                except Exception:
                    step = None
            contract_size = round(contract_size, amount_precision)

            # 防止截断后为0或仍小于最小数量
            if contract_size <= 0 or contract_size < min_amount:
                contract_size = max(min_amount, 10 ** (-amount_precision))
                if step and step > 0:
                    try:
                        contract_size = math.ceil(contract_size / step) * step
                    except Exception:
                        pass
                contract_size = round(contract_size, amount_precision)

            # 若按当前价格计算的成本仍低于分配金额，则按步进/精度向上补量，尽量使 size*price ≥ amount
            try:
                used_usdt = contract_size * current_price
                if used_usdt + 1e-12 < amount:
                    # 计算还需增加的数量
                    need_qty = (amount - used_usdt) / current_price
                    incr_step = step if (step and step > 0) else (10 ** (-amount_precision))
                    # 向上取整到合法步进
                    add_qty = math.ceil(need_qty / incr_step) * incr_step
                    contract_size = round(contract_size + add_qty, amount_precision)
                    # 再次确保不低于最小数量
                    if contract_size < min_amount:
                        contract_size = min_amount
                        if step and step > 0:
                            contract_size = math.ceil(contract_size / step) * step
                        contract_size = round(contract_size, amount_precision)
            except Exception:
                pass

            if contract_size <= 0:
                logger.warning(f"⚠️ {symbol}最终数量无效: {contract_size}")
                return False

            logger.info(f"📝 准备下单: {symbol} {side} 金额:{amount:.4f}U 价格:{current_price:.4f} 数量:{contract_size:.8f}")
            # 成本对齐信息（用于核对是否用满分配金额）
            try:
                est_cost = contract_size * current_price
                logger.info(f"🧮 下单成本对齐: 分配金额={amount:.4f}U | 预计成本={est_cost:.4f}U | 数量={contract_size:.8f} | minSz={min_amount} | lotSz={lot_sz}")
            except Exception:
                pass

            pos_side = 'long' if side == 'buy' else 'short'
            order_id = None
            last_err = None

            # 打印当前 ccxt 版本配置，便于排查
            try:
                ex_ver = getattr(self.exchange, 'version', None)
                opt_ver = (self.exchange.options or {}).get('version') if getattr(self.exchange, 'options', None) else None
                logger.debug(f"🔧 CCXT version: {ex_ver}, options.version: {opt_ver}")
            except Exception:
                pass

            import traceback

            # 可选：仅用原生接口（通过环境变量控制）
            native_only = False
            try:
                native_only = (os.environ.get('USE_OKX_NATIVE_ONLY', '').strip().lower() in ('1', 'true', 'yes'))
            except Exception:
                native_only = False

            # 尝试1：统一接口 create_order（若未启用仅原生）
            if not native_only:
                try:
                    params = {'tdMode': 'cross', 'posSide': pos_side}
                    resp = self.exchange.create_order(symbol, 'market', side, contract_size, None, params)
                    if isinstance(resp, dict):
                        order_id = resp.get('id') or resp.get('orderId') or resp.get('ordId') or resp.get('clOrdId')
                    elif isinstance(resp, list) and resp and isinstance(resp[0], dict):
                        order_id = resp[0].get('id') or resp[0].get('orderId') or resp[0].get('ordId') or resp[0].get('clOrdId')
                    if order_id:
                        logger.info(f"✅ 成功创建{symbol} {side}订单，数量:{contract_size:.8f}，订单ID:{order_id}")
                    else:
                        logger.warning(f"⚠️ create_order 返回未包含订单ID，响应: {resp}")
                except Exception as e1:
                    last_err = e1
                    logger.error(f"❌ create_order 异常: {e1}")
                    logger.debug(traceback.format_exc())

            # 尝试2：create_market_order（若尚未拿到ID且未启用仅原生）
            if not order_id and not native_only:
                try:
                    params = {'tdMode': 'cross', 'posSide': pos_side}
                    resp = self.exchange.create_market_order(symbol, side, contract_size, None, params)  # type: ignore[arg-type]
                    if isinstance(resp, dict):
                        order_id = resp.get('id') or resp.get('orderId') or resp.get('ordId') or resp.get('clOrdId')
                    elif isinstance(resp, list) and resp and isinstance(resp[0], dict):
                        order_id = resp[0].get('id') or resp[0].get('orderId') or resp[0].get('ordId') or resp[0].get('clOrdId')
                    if order_id:
                        logger.info(f"✅ 成功创建{symbol} {side}订单（market API），数量:{contract_size:.8f}，订单ID:{order_id}")
                    else:
                        logger.warning(f"⚠️ create_market_order 返回未包含订单ID，响应: {resp}")
                except Exception as e2:
                    last_err = e2
                    logger.error(f"❌ create_market_order 异常: {e2}")
                    logger.debug(traceback.format_exc())

            # 尝试3：OKX 原生接口（最后兜底）
            if not order_id:
                try:
                    inst_id = self.symbol_to_inst_id(symbol)
                    raw_params = {
                        'instId': inst_id,
                        'tdMode': 'cross',
                        'side': side,
                        'posSide': pos_side,
                        'ordType': 'market',
                        'sz': str(contract_size)
                    }
                    resp = self.exchange.privatePostTradeOrder(raw_params)
                    # 兼容 OKX v5 返回结构
                    if isinstance(resp, dict):
                        data = resp.get('data') or []
                        if isinstance(data, list) and data:
                            order_id = data[0].get('ordId') or data[0].get('clOrdId') or data[0].get('id')
                        else:
                            order_id = resp.get('ordId') or resp.get('clOrdId') or resp.get('id')
                    if order_id:
                        logger.info(f"✅ 成功创建{symbol} {side}订单（OKX原生兜底），数量:{contract_size:.8f}，订单ID:{order_id}")
                    else:
                        logger.error(f"❌ OKX原生下单无订单ID，响应: {resp}")
                except Exception as e3:
                    last_err = e3
                    logger.error(f"❌ OKX原生下单异常: {e3}")
                    logger.debug(traceback.format_exc())

            if order_id:
                time.sleep(2)
                pos = self.get_position(symbol, force_refresh=True)
                # 设置初始 SL/TP（基于最新 ATR）
                try:
                    kl = self.get_klines(symbol, 50)
                    atr_p = int((os.environ.get('ATR_PERIOD') or '14').strip())
                    atr_val = self.calculate_atr(kl, atr_p) if kl else 0.0
                    if pos and pos.get('size', 0) > 0 and atr_val > 0:
                        self._set_initial_sl_tp(symbol, float(pos.get('entry_price', 0) or 0), atr_val, pos.get('side', 'long'))
                        st = self.sl_tp_state.get(symbol)
                        if st:
                            logger.info(f"🎯 初始化SL/TP {symbol}: SL={st['sl']:.6f}, TP={st['tp']:.6f} (N={self.atr_sl_n}, M={self.atr_tp_m}, ATR={atr_val:.6f})")
                            okx_ok = self.place_okx_tp_sl(symbol, float(pos.get('entry_price', 0) or 0), pos.get('side', 'long'), atr_val)
                            if okx_ok:
                                logger.info(f"📌 已在交易所侧挂TP/SL {symbol}")
                            else:
                                logger.warning(f"⚠️ 交易所侧TP/SL挂单失败 {symbol}")
                except Exception:
                    pass
                return True

            # 若三次都失败，抛出最后错误提示
            if last_err:
                logger.error(f"❌ 创建{symbol} {side}订单失败：{last_err}")
            return False

        except Exception as e:
            logger.error(f"❌ 创建{symbol} {side}订单异常: {e}")
            import traceback as _tb
            logger.debug(_tb.format_exc())
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

            import traceback as _tb
            order_id = None
            last_err = None

            # 尝试1：ccxt 统一接口 create_order + reduceOnly
            try:
                params = {'reduceOnly': True, 'posSide': position_side, 'tdMode': 'cross'}
                resp = self.exchange.create_order(symbol, 'market', side, size, None, params)
                if isinstance(resp, dict):
                    order_id = resp.get('id') or resp.get('orderId') or resp.get('ordId') or resp.get('clOrdId')
                elif isinstance(resp, list) and resp and isinstance(resp[0], dict):
                    order_id = resp[0].get('id') or resp[0].get('orderId') or resp[0].get('ordId') or resp[0].get('clOrdId')
            except Exception as e1:
                last_err = e1
                logger.error(f"❌ 平仓 create_order 异常: {e1}")
                logger.debug(_tb.format_exc())

            # 尝试2：ccxt create_market_order + reduceOnly
            if not order_id:
                try:
                    params = {'reduceOnly': True, 'posSide': position_side, 'tdMode': 'cross'}
                    resp = self.exchange.create_market_order(symbol, side, size, None, params)  # type: ignore[arg-type]
                    if isinstance(resp, dict):
                        order_id = resp.get('id') or resp.get('orderId') or resp.get('ordId') or resp.get('clOrdId')
                    elif isinstance(resp, list) and resp and isinstance(resp[0], dict):
                        order_id = resp[0].get('id') or resp[0].get('orderId') or resp[0].get('ordId') or resp[0].get('clOrdId')
                except Exception as e2:
                    last_err = e2
                    logger.error(f"❌ 平仓 create_market_order 异常: {e2}")
                    logger.debug(_tb.format_exc())

            # 尝试3：OKX 原生接口兜底
            if not order_id:
                try:
                    inst_id = self.symbol_to_inst_id(symbol)
                    raw_params = {
                        'instId': inst_id,
                        'tdMode': 'cross',
                        'side': side,
                        'posSide': position_side,
                        'reduceOnly': True,
                        'ordType': 'market',
                        'sz': str(size)
                    }
                    resp = self.exchange.privatePostTradeOrder(raw_params)
                    if isinstance(resp, dict):
                        data = resp.get('data') or []
                        if isinstance(data, list) and data:
                            order_id = data[0].get('ordId') or data[0].get('clOrdId') or data[0].get('id')
                        else:
                            order_id = resp.get('ordId') or resp.get('clOrdId') or resp.get('id')
                except Exception as e3:
                    last_err = e3
                    logger.error(f"❌ 平仓 OKX 原生接口异常: {e3}")
                    logger.debug(_tb.format_exc())

            if order_id:
                logger.info(f"✅ 成功平仓{symbol}，方向: {side}，数量: {size:.6f}，盈亏: {pnl:.2f}U")
                # 记录交易统计
                self.stats.add_trade(symbol, position_side, pnl)
                time.sleep(2)
                self.get_position(symbol, force_refresh=True)
                self.last_position_state[symbol] = 'none'

                if open_reverse:
                    reverse_side = 'sell' if position_side == 'long' else 'buy'
                    amount = self.calculate_order_amount(symbol)
                    if amount > 0:
                        if self.create_order(symbol, reverse_side, amount):
                            logger.info(f"🔁 平仓后已反向开仓 {symbol} -> {reverse_side}")
                return True

            logger.error(f"❌ 平仓{symbol}失败")
            if last_err:
                logger.error(f"❌ 平仓最后错误：{last_err}")
            return False
                
        except Exception as e:
            logger.error(f"❌ 平仓{symbol}失败: {e}")
            return False
    
    def calculate_macd(self, prices: List[float]) -> Dict[str, Any]:
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
    
    def calculate_macd_with_params(self, prices: List[float], f: int, s: int, si: int) -> Dict[str, Any]:
        """按指定参数计算MACD"""
        close_array = np.array(prices)
        ema_fast = pd.Series(close_array).ewm(span=f, adjust=False).mean().values
        ema_slow = pd.Series(close_array).ewm(span=s, adjust=False).mean().values
        macd_line = ema_fast - ema_slow
        signal_line = pd.Series(macd_line).ewm(span=si, adjust=False).mean().values
        histogram = macd_line - signal_line
        return {
            'macd': macd_line[-1],
            'signal': signal_line[-1],
            'histogram': histogram[-1],
            'macd_line': macd_line,
            'signal_line': signal_line
        }
    
    # === 新增：ATR 与 ADX 计算（Wilder算法） ===

    def get_symbol_cfg(self, symbol: str) -> Dict[str, float | str]:
        """返回币种配置；若未配置则使用默认"""
        try:
            cfg = self.symbol_cfg.get(symbol)
            if cfg:
                return cfg
        except Exception:
            pass
        return {"period": 20, "n": 2.0, "m": 3.0, "trigger_pct": 0.010, "trail_pct": 0.006, "update_basis": "close"}

    def _set_initial_sl_tp(self, symbol: str, entry_price: float, atr_val: float, side: str):
        """设置初始 SL/TP：多头 SL=P-N*ATR，TP=P+M*ATR；空头 SL=P+N*ATR，TP=P-M*ATR（使用币种配置n/m）"""
        try:
            if atr_val <= 0 or entry_price <= 0 or side not in ('long', 'short'):
                return
            cfg = self.get_symbol_cfg(symbol)
            n = float(cfg['n']); m = float(cfg['m'])
            if side == 'long':
                sl = entry_price - n * atr_val
                tp = entry_price + m * atr_val
                side_num = 1.0
                # 初始化峰值
                self.trailing_peak[symbol] = max(entry_price, self.trailing_peak.get(symbol, entry_price))
            else:
                sl = entry_price + n * atr_val
                tp = entry_price - m * atr_val
                side_num = -1.0
                # 初始化谷值
                self.trailing_trough[symbol] = min(entry_price, self.trailing_trough.get(symbol, entry_price)) if symbol in self.trailing_trough else entry_price
            self.sl_tp_state[symbol] = {'sl': float(sl), 'tp': float(tp), 'side': side_num, 'entry': float(entry_price)}
        except Exception:
            pass

    def _update_trailing_stop(self, symbol: str, current_price: float, atr_val: float, side: str):
        """动态移动止损（币种配置）：
        - update_basis: 'high' 用最高价更新峰值（long）/最低价更新谷值（short）；'close' 用收盘价/当前价
        - 激活条件：价格相对入场达到 trigger_pct
        - long: SL=max(SL_old, basis-N*ATR, peak*(1-trail_pct)); short: SL=min(SL_old, basis+N*ATR, trough*(1+trail_pct))
        """
        try:
            st = self.sl_tp_state.get(symbol)
            if not st or atr_val <= 0 or current_price <= 0 or side not in ('long', 'short'):
                return
            cfg = self.get_symbol_cfg(symbol)
            n = float(cfg['n']); trigger_pct = float(cfg['trigger_pct']); trail_pct = float(cfg['trail_pct'])
            entry = float(st.get('entry', 0) or 0)
            if entry <= 0:
                return

            # 选择更新基准价
            basis_price = float(current_price)
            # 若有当前K线最高/最低价，可在调用处传入；此处回退使用 current_price
            if side == 'long':
                # 更新峰值
                peak = max(self.trailing_peak.get(symbol, entry), basis_price)
                self.trailing_peak[symbol] = peak
                # 激活条件：涨幅达到 trigger_pct
                activated = (basis_price >= entry * (1 + trigger_pct))
                atr_sl = basis_price - n * atr_val
                percent_sl = peak * (1 - trail_pct) if activated else st['sl']
                new_sl = max(st['sl'], atr_sl, percent_sl)
                if new_sl > st['sl']:
                    st['sl'] = float(new_sl)
            else:
                # 更新谷值
                trough_prev = self.trailing_trough.get(symbol, entry)
                trough = min(trough_prev, basis_price) if trough_prev else basis_price
                self.trailing_trough[symbol] = trough
                # 激活条件：跌幅达到 trigger_pct（相对入场价下跌）
                activated = (basis_price <= entry * (1 - trigger_pct))
                atr_sl = basis_price + n * atr_val
                percent_sl = trough * (1 + trail_pct) if activated else st['sl']
                new_sl = min(st['sl'], atr_sl, percent_sl)
                if new_sl < st['sl']:
                    st['sl'] = float(new_sl)
            self.sl_tp_state[symbol] = st
        except Exception:
            pass
    def place_okx_tp_sl(self, symbol: str, entry_price: float, side: str, atr_val: float) -> bool:
        """在OKX侧同时挂TP/SL条件单；posSide=long→side='sell'，posSide=short→side='buy'；执行价用市价(-1)"""
        try:
            # 已挂过则直接返回
            if self.okx_tp_sl_placed.get(symbol):
                return True
            inst_id = self.symbol_to_inst_id(symbol)
            if not inst_id or entry_price <= 0 or atr_val <= 0 or side not in ('long', 'short'):
                return False
            # 获取当前持仓数量用于 sz（OKX要求 sz 或 closeFraction）
            pos = self.get_position(symbol, force_refresh=True)
            size = float(pos.get('size', 0) or 0)
            if size <= 0:
                logger.warning(f"⚠️ 无有效持仓数量，跳过挂TP/SL {symbol}")
                return False

            # 撤销已挂的TP/SL条件单，避免重复残留
            try:
                self.cancel_symbol_tp_sl(symbol)
                time.sleep(0.3)  # 节流，避免与后续下单竞态
            except Exception:
                pass

            n = float(self.atr_sl_n); m = float(self.atr_tp_m)
            if side == 'long':
                sl_trigger = entry_price - n * atr_val
                tp_trigger = entry_price + m * atr_val
                ord_side = 'sell'
                pos_side = 'long'
            else:
                sl_trigger = entry_price + n * atr_val
                tp_trigger = entry_price - m * atr_val
                ord_side = 'buy'
                pos_side = 'short'
            
            # 钳制触发价：基于最新价方向校验，并按 tick 对齐，避免 51280 风控错误
            try:
                last_price = 0.0
                tkr = self.exchange.publicGetMarketTicker({'instId': inst_id})
                if isinstance(tkr, dict):
                    d = tkr.get('data') or []
                    if isinstance(d, list) and d:
                        last_price = float(d[0].get('last') or d[0].get('lastPx') or 0.0)
                price_prec = int(self.markets_info.get(symbol, {}).get('price_precision', 4))
                tick = 10 ** (-price_prec)
                min_gap = max(0.001 * last_price, 5 * tick) if last_price > 0 else 5 * tick
                if last_price > 0:
                    if side == 'long':
                        # 多头：SL < last，TP > last
                        sl_trigger = min(sl_trigger, last_price - min_gap)
                        tp_trigger = max(tp_trigger, last_price + min_gap)
                        # 步进对齐（保持方向约束）
                        sl_trigger = math.floor(sl_trigger / tick) * tick
                        tp_trigger = math.ceil(tp_trigger / tick) * tick
                    else:
                        # 空头：SL > last，TP < last
                        sl_trigger = max(sl_trigger, last_price + min_gap)
                        tp_trigger = min(tp_trigger, last_price - min_gap)
                        sl_trigger = math.ceil(sl_trigger / tick) * tick
                        tp_trigger = math.floor(tp_trigger / tick) * tick
            except Exception:
                pass

            params = {
                'instId': inst_id,
                'tdMode': 'cross',
                'posSide': pos_side,
                'side': ord_side,
                'ordType': 'oco',
                'reduceOnly': True,
                'sz': f"{size}",
                'tpTriggerPx': f"{tp_trigger}",
                'tpOrdPx': '-1',
                'slTriggerPx': f"{sl_trigger}",
                'slOrdPx': '-1',
            }
            resp = self.exchange.privatePostTradeOrderAlgo(params)
            ok = False
            if isinstance(resp, dict):
                code = str(resp.get('code', ''))
                ok = (code == '0' or code == '200' or (resp.get('data') and not code or code == '0'))
            else:
                ok = bool(resp)
            if ok:
                logger.info(f"📌 交易所侧TP/SL已挂 {symbol}: size={size:.6f} TP@{tp_trigger:.6f} SL@{sl_trigger:.6f}")
                self.okx_tp_sl_placed[symbol] = True
                return True
            else:
                logger.warning(f"⚠️ 交易所侧TP/SL挂单失败 {symbol}: {resp}")
                return False
        except Exception as e:
            logger.warning(f"⚠️ 交易所侧TP/SL挂单异常 {symbol}: {e}")
            return False

    def calculate_atr(self, klines: List[Dict], period: int = 14) -> float:
        """计算 ATR（Wilder），返回最新值；klines需含 high/low/close，按时间升序"""
        try:
            if len(klines) < period + 1:
                return 0.0
            highs = np.array([k['high'] for k in klines], dtype=float)
            lows = np.array([k['low'] for k in klines], dtype=float)
            closes = np.array([k['close'] for k in klines], dtype=float)
            prev_closes = np.concatenate(([closes[0]], closes[:-1]))
            tr = np.maximum(highs - lows, np.maximum(np.abs(highs - prev_closes), np.abs(lows - prev_closes)))
            # Wilder 平滑：先用TR的period均值作为首个ATR，再进行递推
            atr = np.zeros_like(tr)
            atr[period-1] = tr[:period].mean()
            for i in range(period, len(tr)):
                atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
            return float(atr[-1])
        except Exception:
            return 0.0

    def calculate_adx(self, klines: List[Dict], period: int = 14) -> float:
        """计算 ADX（Wilder），返回最新值；klines需含 high/low/close，按时间升序"""
        try:
            if len(klines) < period + 1:
                return 0.0
            highs = np.array([k['high'] for k in klines], dtype=float)
            lows = np.array([k['low'] for k in klines], dtype=float)
            closes = np.array([k['close'] for k in klines], dtype=float)

            up_move = highs[1:] - highs[:-1]
            down_move = lows[:-1] - lows[1:]
            plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
            minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

            prev_closes = closes[:-1]
            tr = np.maximum(highs[1:] - lows[1:], np.maximum(np.abs(highs[1:] - prev_closes), np.abs(lows[1:] - prev_closes)))

            # Wilder 平滑
            def wilder_smooth(arr):
                sm = np.zeros_like(arr)
                sm[period-1] = arr[:period].sum()
                for i in range(period, len(arr)):
                    sm[i] = sm[i-1] - (sm[i-1] / period) + arr[i]
                return sm

            plus_dm_sm = wilder_smooth(plus_dm)
            minus_dm_sm = wilder_smooth(minus_dm)
            tr_sm = wilder_smooth(tr)

            # 避免除零
            tr_sm_safe = np.where(tr_sm == 0, 1e-12, tr_sm)

            plus_di = 100.0 * (plus_dm_sm / tr_sm_safe)
            minus_di = 100.0 * (minus_dm_sm / tr_sm_safe)
            dx = 100.0 * (np.abs(plus_di - minus_di) / np.maximum(plus_di + minus_di, 1e-12))

            # ADX 为 DX 的 Wilder 平滑
            adx = np.zeros_like(dx)
            adx[period-1] = dx[:period].mean()
            for i in range(period, len(dx)):
                adx[i] = (adx[i-1] * (period - 1) + dx[i]) / period

            return float(adx[-1])
        except Exception:
            return 0.0

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

            # === 先做ATR与ADX过滤 ===
            try:
                atr_period = int((os.environ.get('ATR_PERIOD') or '14').strip())
            except Exception:
                atr_period = 14
            try:
                atr_ratio_thresh = float((os.environ.get('ATR_RATIO_THRESH') or '0.004').strip())
            except Exception:
                atr_ratio_thresh = 0.004
            try:
                adx_period = int((os.environ.get('ADX_PERIOD') or '14').strip())
            except Exception:
                adx_period = 14
            try:
                adx_min_trend = float((os.environ.get('ADX_MIN_TREND') or '25').strip())
            except Exception:
                adx_min_trend = 25.0

            close_price = float(closes[-1])
            atr_val = self.calculate_atr(klines, atr_period)
            adx_val = self.calculate_adx(klines, adx_period)

            if atr_val > 0 and close_price > 0:
                atr_ratio = atr_val / close_price
                if atr_ratio < atr_ratio_thresh:
                    logger.debug(f"ATR滤波提示：波动率低（ATR/收盘={atr_ratio:.4f} < {atr_ratio_thresh}），不拦截信号")

            if adx_val > 0 and adx_val < adx_min_trend:
                logger.debug(f"ADX滤波提示：趋势不足（ADX={adx_val:.1f} < {adx_min_trend}），不拦截信号")

            # 使用实时K线：当前与前一根（不等待收盘） - 支持分币种MACD参数
            _p = getattr(self, 'per_symbol_params', {}).get(symbol, {})
            _macd = _p.get('macd') if isinstance(_p, dict) else None
            if isinstance(_macd, tuple) and len(_macd) == 3:
                f, s, si = int(_macd[0]), int(_macd[1]), int(_macd[2])
                macd_current = self.calculate_macd_with_params(closes, f, s, si)
                macd_prev = self.calculate_macd_with_params(closes[:-1], f, s, si)
            else:
                macd_current = self.calculate_macd(closes)
                macd_prev = self.calculate_macd(closes[:-1])
            
            # 获取持仓（强制刷新，确保信号判断基于最新持仓）
            position = self.get_position(symbol, force_refresh=True)
            try:
                logger.debug(f"📏 {symbol} ATR={atr_val:.6f}, ATR/Close={atr_val/close_price:.6f} | ADX={adx_val:.2f}")
            except Exception:
                pass
            # 可选：在日志里输出ATR/ADX，用于回溯
            try:
                logger.debug(f"📏 {symbol} ATR({atr_period})={atr_val:.6f}, ATR/Close={atr_val/close_price:.6f} | ADX({adx_period})={adx_val:.2f}")
            except Exception:
                pass
            
            # 使用实时K线进行交叉与柱状图颜色变化判断
            prev_macd = macd_prev['macd']
            prev_signal = macd_prev['signal']
            prev_hist = macd_prev['histogram']
            current_macd = macd_current['macd']
            current_signal = macd_current['signal']
            current_hist = macd_current['histogram']
            
            logger.debug(f"📊 {symbol} MACD(实时) - 当前: MACD={current_macd:.6f}, Signal={current_signal:.6f}, Hist={current_hist:.6f}")
            
            # 分币种 ADX 硬过滤（若配置了更严格阈值，则不足直接不交易）
            try:
                _p2 = getattr(self, 'per_symbol_params', {}).get(symbol, {})
                _th = float(_p2.get('adx_min_trend', 0) or 0)
                if _th > 0 and adx_val > 0 and adx_val < _th:
                    return {'signal': 'hold', 'reason': f'ADX不足 {adx_val:.1f} < {_th:.1f}'}
            except Exception:
                pass
            
            # 生成交易信号
            if position['size'] == 0:  # 无持仓
                # 双确认开仓：交叉 + 柱状图跨零变色（减少频繁交易）
                buy_cross = (prev_macd <= prev_signal and current_macd > current_signal)
                buy_color = (prev_hist <= 0 and current_hist > 0)
                sell_cross = (prev_macd >= prev_signal and current_macd < current_signal)
                sell_color = (prev_hist >= 0 and current_hist < 0)

                if buy_cross and buy_color:
                    return {'signal': 'buy', 'reason': '双确认：金叉 + 柱状图由负转正'}
                elif sell_cross and sell_color:
                    return {'signal': 'sell', 'reason': '双确认：死叉 + 柱状图由正转负'}
                else:
                    return {'signal': 'hold', 'reason': '等待双确认信号'}
            
            else:  # 有持仓
                current_position_side = position['side']
                
                if current_position_side == 'long':
                    # 多头双确认平仓：死叉且柱状图为负
                    if (prev_macd >= prev_signal and current_macd < current_signal) and (current_hist < 0):
                        return {'signal': 'close', 'reason': '多头双确认平仓：死叉且柱状图为负'}
                    else:
                        return {'signal': 'hold', 'reason': '持有多头'}
                
                else:  # short
                    # 空头双确认平仓：金叉且柱状图为正
                    if (prev_macd <= prev_signal and current_macd > current_signal) and (current_hist > 0):
                        return {'signal': 'close', 'reason': '空头双确认平仓：金叉且柱状图为正'}
                    else:
                        return {'signal': 'hold', 'reason': '持有空头'}
                        
        except Exception as e:
            logger.error(f"❌ 分析{symbol}失败: {e}")
            return {'signal': 'hold', 'reason': f'分析异常: {e}'}
    
    def _throttle(self):
        """简单节流：控制最小 API 调用间隔，保护速率限制"""
        try:
            now = time.time()
            wait = self._min_api_interval - (now - self._last_api_ts)
            if wait and wait > 0:
                time.sleep(wait)
            self._last_api_ts = time.time()
        except Exception:
            pass

    def execute_strategy(self):
        """执行策略"""
        logger.info("=" * 70)
        logger.info(f"🚀 开始执行MACD策略 (分币种杠杆，{self.timeframe} 周期)")
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
                
                # 获取当前持仓（强制刷新，确保动作基于最新状态）
                current_position = self.get_position(symbol, force_refresh=True)
                
                # 优先进行 SL/TP 检查与跟踪止损更新（触发则直接平仓，不反手）
                try:
                    kl = self.get_klines(symbol, 50)
                    if kl:
                        close_price = float(kl[-1]['close'])
                        atr_p = int((os.environ.get('ATR_PERIOD') or '14').strip())
                        atr_val = self.calculate_atr(kl, atr_p)
                        if current_position and current_position.get('size', 0) > 0 and atr_val > 0:
                            self._update_trailing_stop(symbol, close_price, atr_val, current_position.get('side', 'long'))
                            st = self.sl_tp_state.get(symbol)
                            if st:
                                try:
                                    entry_px = float(st.get('entry', 0) or 0)
                                    if entry_px > 0 and atr_val > 0:
                                        profit = (close_price - entry_px) if current_position.get('side') == 'long' else (entry_px - close_price)
                                        if profit >= 2.5 * atr_val:
                                            st['sl'] = max(st['sl'], close_price - 1.0 * atr_val) if current_position.get('side') == 'long' else min(st['sl'], close_price + 1.0 * atr_val)
                                        elif profit >= 1.5 * atr_val:
                                            st['sl'] = max(st['sl'], close_price - 1.2 * atr_val) if current_position.get('side') == 'long' else min(st['sl'], close_price + 1.2 * atr_val)
                                except Exception:
                                    pass
                                try:
                                    # 动态止盈收紧后，撤旧重挂交易所侧TP/SL
                                    self.okx_tp_sl_placed[symbol] = False
                                    self.cancel_symbol_tp_sl(symbol)
                                    self.place_okx_tp_sl(symbol, entry_px, current_position.get('side', 'long'), atr_val)
                                    logger.info(f"🔁 更新追踪止盈：已撤旧单并重挂 {symbol}")
                                except Exception as _e:
                                    logger.warning(f"⚠️ 更新追踪止盈重挂失败 {symbol}: {_e}")
                                if current_position.get('side') == 'long':
                                    if close_price <= st['sl'] or close_price >= st['tp']:
                                        logger.info(f"⛔ 触发SL/TP多头 {symbol}: 价={close_price:.6f} SL={st['sl']:.6f} TP={st['tp']:.6f}")
                                        self.close_position(symbol, open_reverse=False)
                                        current_position = self.get_position(symbol, force_refresh=True)
                                        continue
                                else:  # short
                                    if close_price >= st['sl'] or close_price <= st['tp']:
                                        logger.info(f"⛔ 触发SL/TP空头 {symbol}: 价={close_price:.6f} SL={st['sl']:.6f} TP={st['tp']:.6f}")
                                        self.close_position(symbol, open_reverse=False)
                                        current_position = self.get_position(symbol, force_refresh=True)
                                        continue
                except Exception:
                    pass
                
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
                    # 平仓；是否反手按分币种策略
                    _pp = getattr(self, 'per_symbol_params', {}).get(symbol, {})
                    allow_reverse = bool(_pp.get('allow_reverse', True)) if isinstance(_pp, dict) else True
                    if self.close_position(symbol, open_reverse=allow_reverse):
                        if allow_reverse:
                            logger.info(f"✅ 平仓并反手开仓 {symbol} 成功 - {reason}")
                        else:
                            logger.info(f"✅ 平仓完成（不反手） {symbol} - {reason}")
            
            logger.info("=" * 70)
                        
        except Exception as e:
            logger.error(f"❌ 执行策略失败: {e}")
    
    def run_continuous(self, interval: int = 60):
        """连续运行策略（改为北京时间整点刷新）"""
        logger.info("=" * 70)
        logger.info("🚀 MACD策略启动 - RAILWAY平台版 (小币种)")
        logger.info("=" * 70)
        logger.info(f"📈 MACD参数: 快线={self.fast_period}, 慢线={self.slow_period}, 信号线={self.signal_period}")
        logger.info(f"📊 K线周期: {self.timeframe}")
        lev_desc = ', '.join([f"{s.split('/')[0]}={self.symbol_leverage.get(s, 20)}x" for s in self.symbols])
        logger.info(f"💪 杠杆倍数: {lev_desc}")
        logger.info("⏰ 刷新方式: 实时巡检（每interval秒执行一次，可用环境变量 SCAN_INTERVAL 调整，默认1秒）")
        logger.info(f"🔄 状态同步: 每{self.sync_interval}秒")
        logger.info(f"📊 监控币种: {', '.join(self.symbols)}")
        logger.info(f"💡 小币种特性: 支持0.1U起的小额交易")
        logger.info(self.stats.get_summary())
        logger.info("=" * 70)

        china_tz = pytz.timezone('Asia/Shanghai')

        while True:
            try:
                # 实时巡检模式：每 interval 秒执行一次
                start_ts = time.time()

                # 按需同步状态（内部有节流）
                self.check_sync_needed()

                # 执行策略（含拉取行情、分析与下单）
                self.execute_strategy()

                # 计算本轮耗时与休眠
                elapsed = time.time() - start_ts
                sleep_sec = max(1, int(interval - elapsed)) if interval > 0 else 1
                logger.info(f"⏳ 休眠 {sleep_sec} 秒后继续实时巡检...")
                time.sleep(sleep_sec)

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
        logger.error("💡 请在RAILWAY平台上设置这些环境变量")
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
        
        # 运行策略（扫描间隔可通过环境变量 SCAN_INTERVAL 覆盖，单位秒，默认1s）
        try:
            scan_interval_env = os.environ.get('SCAN_INTERVAL', '').strip()
            scan_interval = int(scan_interval_env) if scan_interval_env else 2
            if scan_interval <= 0:
                scan_interval = 1
        except Exception:
            scan_interval = 1
        logger.info(f"🛠 扫描间隔设置: {scan_interval} 秒（可用环境变量 SCAN_INTERVAL 覆盖）")
        strategy.run_continuous(interval=scan_interval)
        
    except Exception as e:
        logger.error(f"❌ 策略初始化或运行失败: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main()
