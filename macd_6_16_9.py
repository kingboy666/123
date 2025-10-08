#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MACD策略实现
20倍杠杆，智能仓位分配
"""
import time
import logging
import datetime
import os
from typing import Dict, Any, List

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
        
        # 杠杆配置
        self.max_leverage = 25  # 最高杠杆倍数
        self.min_leverage = 20  # 最低杠杆倍数
        
        # 仓位配置
        self.position_percentage = 0.8  # 使用账户80%资金
        self.min_order_value = 0.1  # 最小下单金额
        
        # 持仓记录
        self.positions: Dict[str, Any] = {}
        
        # 初始化交易所
        self._setup_exchange()
    
    def get_smart_leverage(self, symbol: str, account_balance: float = 1000) -> int:
        """根据币种和账户大小智能计算杠杆倍数"""
        # 使用最低20倍杠杆
        return self.min_leverage
    
    def _setup_exchange(self):
        """设置交易所配置"""
        try:
            # 检查连接
            self.exchange.check_required_credentials()
            
            # 设置杠杆
            for symbol in self.symbols:
                # 使用智能杠杆计算
                leverage = self.get_smart_leverage(symbol)
                # CCXT OKX的set_leverage需要添加参数
                self.exchange.set_leverage(leverage, symbol, {'marginMode': 'cross'})
                logger.info(f"设置{symbol}杠杆为{leverage}倍")
            
            # 设置合约模式
            self.exchange.set_position_mode(False)  # 单向持仓模式
            logger.info("设置为单向持仓模式")
            
        except Exception as e:
            logger.error(f"交易所设置失败: {e}")
            raise
    
    def get_account_balance(self) -> float:
        """获取账户余额"""
        try:
            balance = self.exchange.fetch_balance()
            return float(balance['USDT']['free'])
        except Exception as e:
            logger.error(f"获取账户余额失败: {e}")
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
            logger.error(f"获取{symbol}K线数据失败: {e}")
            return []
    
    def get_position(self, symbol: str) -> Dict:
        """获取当前持仓"""
        try:
            positions = self.exchange.fetch_positions([symbol])
            for position in positions:
                if position['symbol'] == symbol:
                    return {
                        'size': float(position.get('contracts', 0) or 0),
                        'side': position.get('side', 'none'),
                        'entry_price': float(position.get('entryPrice', 0) or 0),
                        'unrealized_pnl': float(position.get('unrealizedPnl', 0) or 0)
                    }
            return {'size': 0, 'side': 'none', 'entry_price': 0, 'unrealized_pnl': 0}
        except Exception as e:
            logger.error(f"获取{symbol}持仓失败: {e}")
            return {'size': 0, 'side': 'none', 'entry_price': 0, 'unrealized_pnl': 0}
    
    def calculate_order_amount(self, symbol: str, price: float = 0) -> float:
        """计算下单金额（平均分配）"""
        try:
            balance = self.get_account_balance()
            total_amount = balance * self.position_percentage
            
            # 平均分配到每个交易对
            allocated_amount = total_amount / len(self.symbols)
            
            # 确保不管金额多小都能下单，移除min_order_value限制
            order_amount = allocated_amount
            
            logger.info(f"{symbol}分配金额: {order_amount:.2f} USDT")
            return order_amount
            
        except Exception as e:
            logger.error(f"计算{symbol}下单金额失败: {e}")
            return float(self.min_order_value)
    
    def create_order(self, symbol: str, side: str, amount: float) -> bool:
        """创建订单"""
        try:
            # 获取当前价格
            ticker = self.exchange.fetch_ticker(symbol)
            current_price = float(ticker['last'])
            
            # 计算合约数量
            contract_size = amount / current_price
            
            # 创建市价单
            order = self.exchange.create_market_order(symbol, side, contract_size)
            
            if order['id']:
                logger.info(f"成功创建{symbol} {side}订单，金额: {amount:.2f} USDT")
                return True
            else:
                logger.error(f"创建{symbol} {side}订单失败")
                return False
                
        except Exception as e:
            logger.error(f"创建{symbol} {side}订单异常: {e}")
            return False
    
    def close_position(self, symbol: str) -> bool:
        """平仓"""
        try:
            position = self.get_position(symbol)
            if position['size'] == 0:
                logger.info(f"{symbol}无持仓，无需平仓")
                return True
            
            # 计算合约数量
            size = float(position.get('size', 0) or 0)
            
            # 反向平仓：多头平仓用sell，空头平仓用buy
            side = 'sell' if position.get('side') == 'long' else 'buy'
            
            # 直接使用合约数量创建市价单
            order = self.exchange.create_market_order(symbol, side, size)
            
            if order['id']:
                logger.info(f"成功平仓{symbol}，方向: {side}，数量: {size}")
                return True
            else:
                logger.error(f"平仓{symbol}失败")
                return False
                
        except Exception as e:
            logger.error(f"平仓{symbol}失败: {e}")
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
            'histogram': histogram[-1]
        }
    
    def analyze_symbol(self, symbol: str) -> Dict[str, str]:
        """分析单个交易对"""
        try:
            # 获取K线数据
            klines = self.get_klines(symbol, 100)  # 获取更多数据以确保MACD计算准确
            if not klines:
                return {'signal': 'hold', 'reason': '数据获取失败'}
            
            # 提取收盘价
            closes = [kline['close'] for kline in klines]
            
            # 计算MACD
            macd_data = self.calculate_macd(closes)
            
            # 获取持仓
            position = self.get_position(symbol)
            
            # 生成交易信号
            if position['size'] == 0:  # 无持仓
                # 金叉信号：MACD线上穿信号线且柱状图从负变正
                if len(closes) > self.slow_period + self.signal_period + 1:
                    prev_macd = self.calculate_macd(closes[:-1])
                    # 确保是真正的金叉（MACD线从下往上穿过信号线）
                    if (prev_macd['macd'] <= prev_macd['signal'] and 
                        macd_data['macd'] > macd_data['signal'] and 
                        macd_data['histogram'] > 0):
                        return {'signal': 'buy', 'reason': 'MACD金叉'}
                    # 确保是真正的死叉（MACD线从上往下穿过信号线）
                    elif (prev_macd['macd'] >= prev_macd['signal'] and 
                          macd_data['macd'] < macd_data['signal'] and 
                          macd_data['histogram'] < 0):
                        return {'signal': 'sell', 'reason': 'MACD死叉'}
                    else:
                        return {'signal': 'hold', 'reason': '等待明确的交叉信号'}
                else:
                    return {'signal': 'hold', 'reason': '数据不足，无法确认交叉信号'}
            else:  # 有持仓
                if position['side'] == 'long':
                    # 多头平仓信号：MACD线下穿信号线且柱状图为负
                    if macd_data['macd'] < macd_data['signal'] and macd_data['histogram'] < 0:
                        return {'signal': 'close', 'reason': '多头平仓信号'}
                    else:
                        return {'signal': 'hold', 'reason': '持有多头'}
                else:  # short
                    # 空头平仓信号：MACD线上穿信号线且柱状图为正
                    if macd_data['macd'] > macd_data['signal'] and macd_data['histogram'] > 0:
                        return {'signal': 'close', 'reason': '空头平仓信号'}
                    else:
                        return {'signal': 'hold', 'reason': '持有空头'}
                        
        except Exception as e:
            logger.error(f"分析{symbol}失败: {e}")
            return {'signal': 'hold', 'reason': f'分析异常: {e}'}
    
    def execute_strategy(self):
        """执行策略"""
        logger.info("开始执行MACD策略...")
        
        try:
            # 分析所有交易对
            signals = {}
            for symbol in self.symbols:
                signals[symbol] = self.analyze_symbol(symbol)
                logger.info(f"{symbol}信号: {signals[symbol]}")
            
            # 执行交易
            for symbol, signal_info in signals.items():
                signal = signal_info['signal']
                reason = signal_info['reason']
                
                if signal == 'buy':
                    amount = self.calculate_order_amount(symbol)
                    if self.create_order(symbol, 'buy', amount):
                        logger.info(f"开多{symbol}成功")
                
                elif signal == 'sell':
                    amount = self.calculate_order_amount(symbol)
                    if self.create_order(symbol, 'sell', amount):
                        logger.info(f"开空{symbol}成功")
                
                elif signal == 'close':
                    if self.close_position(symbol):
                        logger.info(f"平仓{symbol}成功")
                        
        except Exception as e:
            logger.error(f"执行策略失败: {e}")
    
    def run_continuous(self, interval: int = 900):
        """连续运行策略"""
        logger.info("策略开始运行...")
        
        while True:
            try:
                self.execute_strategy()
                logger.info(f"等待下次执行，间隔{interval}秒...")
                time.sleep(interval)
                
            except KeyboardInterrupt:
                logger.info("用户中断，策略停止")
                break
            except Exception as e:
                logger.error(f"策略运行异常: {e}")
                # 遇到异常继续尝试，不终止程序
                time.sleep(interval)

def main():
    """主函数"""
    # 从环境变量获取API配置
    okx_api_key = os.environ.get('OKX_API_KEY', '')
    okx_secret_key = os.environ.get('OKX_SECRET_KEY', '')
    okx_passphrase = os.environ.get('OKX_PASSPHRASE', '')
    
    # 检查环境变量是否设置
    if not okx_api_key:
        logger.error("未设置OKX_API_KEY环境变量")
    if not okx_secret_key:
        logger.error("未设置OKX_SECRET_KEY环境变量")
    if not okx_passphrase:
        logger.error("未设置OKX_PASSPHRASE环境变量")
        
    if not (okx_api_key and okx_secret_key and okx_passphrase):
        logger.error("缺少必要的API配置，程序退出")
        return
    
    # 创建策略实例
    try:
        strategy = MACDStrategy(
            api_key=okx_api_key,
            secret_key=okx_secret_key,
            passphrase=okx_passphrase
        )
        
        # 运行策略
        strategy.run_continuous()
        
    except Exception as e:
        logger.error(f"策略初始化或运行失败: {e}")

if __name__ == "__main__":
    main()