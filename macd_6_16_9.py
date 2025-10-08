#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MACD策略实现 - RAILWALL平台版本
25倍杠杆，无限制交易，带挂单识别和状态同步
"""
import time
import logging
import datetime
import os
from typing import Dict, Any, List, Optional

import ccxt
import pandas as pd
import numpy as np

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

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
            }
        })
        
        # 交易对配置
        self.symbols = [
            'FIL/USDT:USDT',
            'SOL/USDT:USDT',
            'ETH/USDT:USDT',
            'BTC/USDT:USDT'
        ]
        
        # 时间周期
        self.timeframe = '15m'
        
        # MACD参数
        self.fast_period = 6
        self.slow_period = 16
        self.signal_period = 9
        
        # 杠杆配置 - 固定25倍
        self.leverage = 25
        
        # 仓位配置 - 使用100%资金
        self.position_percentage = 1.0
        
        # 持仓和挂单缓存
        self.positions_cache: Dict[str, Dict] = {}
        self.open_orders_cache: Dict[str, List] = {}
        self.last_sync_time: float = 0
        self.sync_interval: int = 60  # 60秒同步一次状态
        
        # 初始化交易所
        self._setup_exchange()
        
        # 首次同步状态
        self.sync_all_status()
    
    def _setup_exchange(self):
        """设置交易所配置"""
        try:
            # 检查连接
            self.exchange.check_required_credentials()
            logger.info("✅ API连接验证成功")
            
            # 同步交易所时间
            self.sync_exchange_time()
            
            # 设置杠杆为25倍
            for symbol in self.symbols:
                try:
                    self.exchange.set_leverage(self.leverage, symbol, {'marginMode': 'cross'})
                    logger.info(f"✅ 设置{symbol}杠杆为{self.leverage}倍")
                except Exception as e:
                    logger.warning(f"⚠️ 设置{symbol}杠杆失败（可能已设置）: {e}")
            
            # 设置合约模式
            try:
                self.exchange.set_position_mode(False)  # 单向持仓模式
                logger.info("✅ 设置为单向持仓模式")
            except Exception as e:
                logger.warning(f"⚠️ 设置持仓模式失败（可能已设置）: {e}")
            
        except Exception as e:
            logger.error(f"❌ 交易所设置失败: {e}")
            raise
    
    def sync_exchange_time(self):
        """同步交易所时间"""
        try:
            server_time = self.exchange.fetch_time()
            local_time = int(time.time() * 1000)
            time_diff = server_time - local_time
            
            server_dt = datetime.datetime.fromtimestamp(server_time / 1000)
            local_dt = datetime.datetime.fromtimestamp(local_time / 1000)
            
            logger.info(f"🕐 服务器时间: {server_dt.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"🕐 本地时间: {local_dt.strftime('%Y-%m-%d %H:%M:%S')}")
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
            orders = self.exchange.fetch_open_orders(symbol)
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
            for symbol in self.symbols:
                # 同步持仓
                position = self.get_position(symbol, force_refresh=True)
                self.positions_cache[symbol] = position
                
                # 同步挂单
                orders = self.get_open_orders(symbol)
                self.open_orders_cache[symbol] = orders
                
                # 输出状态
                if position['size'] > 0:
                    logger.info(f"📊 {symbol} 持仓: {position['side']} {position['size']:.6f} @{position['entry_price']:.2f} PNL:{position['unrealized_pnl']:.2f}")
                
                if orders:
                    logger.info(f"📋 {symbol} 挂单数量: {len(orders)}")
                    for order in orders:
                        logger.info(f"   └─ {order['side']} {order['amount']:.6f} @{order.get('price', 'market')}")
            
            self.last_sync_time = time.time()
            logger.info("✅ 状态同步完成")
            
        except Exception as e:
            logger.error(f"❌ 同步状态失败: {e}")
    
    def check_sync_needed(self):
        """检查是否需要同步状态"""
        current_time = time.time()
        if current_time - self.last_sync_time >= self.sync_interval:
            self.sync_all_status()
    
    def get_account_balance(self) -> float:
        """获取账户余额"""
        try:
            balance = self.exchange.fetch_balance()
            free_balance = float(balance['USDT']['free'])
            total_balance = float(balance['USDT']['total'])
            used_balance = float(balance['USDT']['used'])
            
            logger.debug(f"💰 余额 - 可用: {free_balance:.2f} 总额: {total_balance:.2f} 占用: {used_balance:.2f}")
            return free_balance
        except Exception as e:
            logger.error(f"❌ 获取账户余额失败: {e}")
            return 0
    
    def get_klines(self, symbol: str, limit: int = 100) -> List[Dict]:
        """获取K线数据"""
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
            positions = self.exchange.fetch_positions([symbol])
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
            
            # 无论金额多小都返回，不设置最小限制
            logger.debug(f"💵 {symbol}分配金额: {allocated_amount:.4f} USDT (总余额: {balance:.2f} USDT)")
            return allocated_amount
            
        except Exception as e:
            logger.error(f"❌ 计算{symbol}下单金额失败: {e}")
            return 0
    
    def create_order(self, symbol: str, side: str, amount: float) -> bool:
        """创建订单 - 无限制版本"""
        try:
            # 检查是否有挂单
            if self.has_open_orders(symbol):
                logger.warning(f"⚠️ {symbol}存在未成交订单，先取消")
                self.cancel_all_orders(symbol)
                time.sleep(1)  # 等待订单取消
            
            # 如果金额太小，直接返回失败但不报错
            if amount <= 0:
                logger.warning(f"⚠️ {symbol}下单金额为0，跳过")
                return False
            
            # 获取当前价格
            ticker = self.exchange.fetch_ticker(symbol)
            current_price = float(ticker['last'])
            
            # 计算合约数量
            contract_size = amount / current_price
            
            logger.info(f"📝 准备下单: {symbol} {side} 金额:{amount:.4f} USDT 价格:{current_price:.2f} 数量:{contract_size:.6f}")
            
            # 创建市价单
            order = self.exchange.create_market_order(symbol, side, contract_size)
            
            if order['id']:
                logger.info(f"✅ 成功创建{symbol} {side}订单，金额: {amount:.4f} USDT，数量: {contract_size:.6f}")
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
    
    def close_position(self, symbol: str) -> bool:
        """平仓"""
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
            
            # 获取合约数量
            size = float(position.get('size', 0) or 0)
            
            # 反向平仓：多头平仓用sell，空头平仓用buy
            side = 'sell' if position.get('side') == 'long' else 'buy'
            
            logger.info(f"📝 准备平仓: {symbol} {side} 数量:{size:.6f}")
            
            # 直接使用合约数量创建市价单
            order = self.exchange.create_market_order(symbol, side, size)
            
            if order['id']:
                logger.info(f"✅ 成功平仓{symbol}，方向: {side}，数量: {size:.6f}")
                # 等待平仓成交后刷新持仓
                time.sleep(2)
                self.get_position(symbol, force_refresh=True)
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
            
            # 提取收盘价
            closes = [kline['close'] for kline in klines]
            
            # 计算MACD
            macd_data = self.calculate_macd(closes)
            
            # 获取持仓（使用缓存，避免频繁请求）
            position = self.get_position(symbol, force_refresh=False)
            
            # 获取前一根K线的MACD数据用于判断交叉
            if len(closes) > 1:
                prev_macd_data = self.calculate_macd(closes[:-1])
                prev_macd = prev_macd_data['macd']
                prev_signal = prev_macd_data['signal']
            else:
                return {'signal': 'hold', 'reason': '数据不足'}
            
            current_macd = macd_data['macd']
            current_signal = macd_data['signal']
            
            logger.debug(f"📊 {symbol} MACD - 当前: MACD={current_macd:.6f}, Signal={current_signal:.6f}, Hist={macd_data['histogram']:.6f}")
            
            # 生成交易信号
            if position['size'] == 0:  # 无持仓
                # 金叉信号：快线上穿慢线（做多）
                if prev_macd <= prev_signal and current_macd > current_signal:
                    return {'signal': 'buy', 'reason': 'MACD金叉（快线上穿慢线）'}
                
                # 死叉信号：快线下穿慢线（做空）
                elif prev_macd >= prev_signal and current_macd < current_signal:
                    return {'signal': 'sell', 'reason': 'MACD死叉（快线下穿慢线）'}
                
                else:
                    return {'signal': 'hold', 'reason': '等待交叉信号'}
            
            else:  # 有持仓
                if position['side'] == 'long':
                    # 多头平仓：快线下穿慢线（死叉）
                    if prev_macd >= prev_signal and current_macd < current_signal:
                        return {'signal': 'close', 'reason': '多头平仓（死叉）'}
                    else:
                        return {'signal': 'hold', 'reason': '持有多头'}
                
                else:  # short
                    # 空头平仓：快线上穿慢线（金叉）
                    if prev_macd <= prev_signal and current_macd > current_signal:
                        return {'signal': 'close', 'reason': '空头平仓（金叉）'}
                    else:
                        return {'signal': 'hold', 'reason': '持有空头'}
                        
        except Exception as e:
            logger.error(f"❌ 分析{symbol}失败: {e}")
            return {'signal': 'hold', 'reason': f'分析异常: {e}'}
    
    def execute_strategy(self):
        """执行策略"""
        logger.info("=" * 70)
        logger.info("🚀 开始执行MACD策略 (25倍杠杆，无限制交易)")
        logger.info("=" * 70)
        
        try:
            # 检查是否需要同步状态
            self.check_sync_needed()
            
            # 显示当前余额
            balance = self.get_account_balance()
            logger.info(f"💰 当前账户余额: {balance:.2f} USDT")
            
            # 分析所有交易对
            signals = {}
            for symbol in self.symbols:
                signals[symbol] = self.analyze_symbol(symbol)
                position = self.get_position(symbol, force_refresh=False)
                open_orders = self.get_open_orders(symbol)
                
                status_line = f"📊 {symbol}: 信号={signals[symbol]['signal']}, 原因={signals[symbol]['reason']}"
                if position['size'] > 0:
                    status_line += f", 持仓={position['side']} {position['size']:.6f} PNL={position['unrealized_pnl']:.2f}"
                if open_orders:
                    status_line += f", 挂单={len(open_orders)}个"
                
                logger.info(status_line)
            
            # 执行交易
            for symbol, signal_info in signals.items():
                signal = signal_info['signal']
                reason = signal_info['reason']
                
                if signal == 'buy':
                    # 做多：金叉信号
                    amount = self.calculate_order_amount(symbol)
                    if amount > 0:
                        if self.create_order(symbol, 'buy', amount):
                            logger.info(f"🚀 开多{symbol}成功 - {reason}")
                
                elif signal == 'sell':
                    # 做空：死叉信号
                    amount = self.calculate_order_amount(symbol)
                    if amount > 0:
                        if self.create_order(symbol, 'sell', amount):
                            logger.info(f"📉 开空{symbol}成功 - {reason}")
                
                elif signal == 'close':
                    # 平仓
                    if self.close_position(symbol):
                        logger.info(f"✅ 平仓{symbol}成功 - {reason}")
            
            logger.info("=" * 70)
                        
        except Exception as e:
            logger.error(f"❌ 执行策略失败: {e}")
    
    def run_continuous(self, interval: int = 900):
        """连续运行策略"""
        logger.info("=" * 70)
        logger.info("🚀 MACD策略启动 - RAILWALL平台版")
        logger.info("=" * 70)
        logger.info(f"📈 MACD参数: 快线={self.fast_period}, 慢线={self.slow_period}, 信号线={self.signal_period}")
        logger.info(f"💪 杠杆倍数: {self.leverage}倍")
        logger.info(f"⏰ 运行间隔: {interval}秒 ({interval/60:.1f}分钟)")
        logger.info(f"🔄 状态同步: 每{self.sync_interval}秒")
        logger.info(f"📊 监控币种: {', '.join(self.symbols)}")
        logger.info("=" * 70)
        
        while True:
            try:
                self.execute_strategy()
                logger.info(f"⏳ 等待下次执行，间隔{interval}秒 ({interval/60:.1f}分钟)...")
                logger.info("")
                time.sleep(interval)
                
            except KeyboardInterrupt:
                logger.info("⛔ 用户中断，策略停止")
                break
            except Exception as e:
                logger.error(f"❌ 策略运行异常: {e}")
                logger.info("🔄 60秒后重试...")
                # 遇到异常等待后继续尝试，不终止程序
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
        
        # 运行策略
        strategy.run_continuous()
        
    except Exception as e:
        logger.error(f"❌ 策略初始化或运行失败: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main()