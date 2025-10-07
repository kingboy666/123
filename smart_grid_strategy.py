import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Optional, Tuple

class SmartGridStrategy:
    """
    智能均值回归网格策略
    专用于BTC/ETH的5分钟图震荡市交易
    """
    
    def __init__(self):
        self.grid_levels = 5  # 网格层数
        self.grid_spacing = 0.02  # 网格间距 2%
        self.position_size = 0.1  # 每层仓位大小
        self.max_exposure = 0.5  # 最大总暴露
        self.atr_period = 14  # ATR周期
        self.bb_period = 20  # 布林带周期
        self.bb_std = 2.0  # 布林带标准差
        self.kc_period = 20  # 肯特纳通道周期
        self.kc_multiplier = 2.0  # 肯特纳通道乘数
        
        # 网格状态
        self.grid_positions = {}  # 当前网格持仓
        self.entry_prices = {}  # 入场价格
        self.grid_levels_active = {}  # 活跃网格层
        
        # 日志
        self.logger = logging.getLogger(__name__)
    
    def calculate_atr(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
        """计算平均真实波幅(ATR)"""
        try:
            high_low = high - low
            high_close_prev = abs(high - close.shift(1))
            low_close_prev = abs(low - close.shift(1))
            
            true_range = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
            atr = true_range.rolling(window=period).mean().iloc[-1]
            return float(atr) if not pd.isna(atr) else 0.0
        except Exception as e:
            self.logger.error(f"计算ATR错误: {e}")
            return 0.0
    
    def calculate_bollinger_bands(self, close: pd.Series, period: int = 20, std: float = 2.0) -> Tuple[float, float, float]:
        """计算布林带"""
        try:
            sma = close.rolling(window=period).mean().iloc[-1]
            std_dev = close.rolling(window=period).std().iloc[-1]
            
            upper_band = sma + (std_dev * std)
            lower_band = sma - (std_dev * std)
            
            return float(sma), float(upper_band), float(lower_band)
        except Exception as e:
            self.logger.error(f"计算布林带错误: {e}")
            return 0.0, 0.0, 0.0
    
    def calculate_keltner_channel(self, high: pd.Series, low: pd.Series, close: pd.Series, 
                                period: int = 20, multiplier: float = 2.0) -> Tuple[float, float, float]:
        """计算肯特纳通道"""
        try:
            typical_price = (high + low + close) / 3
            ema = typical_price.ewm(span=period).mean().iloc[-1]
            
            atr = self.calculate_atr(high, low, close, period)
            upper_kc = ema + (atr * multiplier)
            lower_kc = ema - (atr * multiplier)
            
            return float(ema), float(upper_kc), float(lower_kc)
        except Exception as e:
            self.logger.error(f"计算肯特纳通道错误: {e}")
            return 0.0, 0.0, 0.0
    
    def detect_market_regime(self, close: pd.Series, bb_width_threshold: float = 0.05) -> str:
        """检测市场状态：震荡市或趋势市"""
        try:
            # 计算布林带宽度
            _, bb_upper, bb_lower = self.calculate_bollinger_bands(close, self.bb_period, self.bb_std)
            bb_width = (bb_upper - bb_lower) / ((bb_upper + bb_lower) / 2)
            
            # 计算价格波动率
            volatility = close.pct_change().std() * np.sqrt(252)  # 年化波动率
            
            # 判断市场状态
            if bb_width < bb_width_threshold and volatility < 0.3:
                return "sideways"  # 震荡市
            else:
                return "trending"  # 趋势市
                
        except Exception as e:
            self.logger.error(f"检测市场状态错误: {e}")
            return "sideways"  # 默认震荡市
    
    def setup_grid_levels(self, current_price: float, symbol: str) -> Dict[int, Dict]:
        """设置网格层级"""
        grid_levels = {}
        base_level = int(np.log(current_price) / np.log(1 + self.grid_spacing))
        
        for i in range(-self.grid_levels, self.grid_levels + 1):
            level_price = current_price * ((1 + self.grid_spacing) ** i)
            grid_levels[i] = {
                'price': level_price,
                'position': 0,
                'size': self.position_size,
                'active': False
            }
        
        self.grid_positions[symbol] = grid_levels
        return grid_levels
    
    def calculate_grid_signal(self, symbol: str, current_price: float, 
                            high: pd.Series, low: pd.Series, close: pd.Series) -> Dict:
        """计算网格交易信号"""
        try:
            # 检测市场状态
            market_regime = self.detect_market_regime(close)
            
            if market_regime != "sideways":
                return {'action': 'hold', 'reason': '市场处于趋势市，不适合网格交易'}
            
            # 计算技术指标
            bb_middle, bb_upper, bb_lower = self.calculate_bollinger_bands(close)
            kc_middle, kc_upper, kc_lower = self.calculate_keltner_channel(high, low, close)
            atr = self.calculate_atr(high, low, close)
            
            # 初始化网格
            if symbol not in self.grid_positions:
                self.setup_grid_levels(current_price, symbol)
            
            grid_levels = self.grid_positions[symbol]
            
            # 寻找最近的网格层级
            closest_level = None
            min_distance = float('inf')
            
            for level, grid_info in grid_levels.items():
                distance = abs(current_price - grid_info['price']) / current_price
                if distance < min_distance:
                    min_distance = distance
                    closest_level = level
            
            # 检查是否需要开仓或平仓
            actions = []
            total_exposure = 0
            
            for level, grid_info in grid_levels.items():
                if grid_info['position'] != 0:
                    total_exposure += abs(grid_info['position']) * grid_info['size']
                
                # 检查平仓条件
                if grid_info['position'] > 0 and current_price >= grid_info['price'] * (1 + self.grid_spacing):
                    actions.append({
                        'action': 'close_long',
                        'level': level,
                        'price': grid_info['price'],
                        'size': grid_info['size']
                    })
                elif grid_info['position'] < 0 and current_price <= grid_info['price'] * (1 - self.grid_spacing):
                    actions.append({
                        'action': 'close_short', 
                        'level': level,
                        'price': grid_info['price'],
                        'size': grid_info['size']
                    })
            
            # 检查开仓条件（总暴露不超过限制）
            if total_exposure < self.max_exposure:
                # 价格接近布林带下轨且低于肯特纳通道下轨 - 开多
                if current_price <= bb_lower and current_price <= kc_lower:
                    actions.append({
                        'action': 'open_long',
                        'level': closest_level,
                        'price': current_price,
                        'size': self.position_size
                    })
                # 价格接近布林带上轨且高于肯特纳通道上轨 - 开空
                elif current_price >= bb_upper and current_price >= kc_upper:
                    actions.append({
                        'action': 'open_short',
                        'level': closest_level, 
                        'price': current_price,
                        'size': self.position_size
                    })
            
            if actions:
                return {
                    'action': 'execute',
                    'actions': actions,
                    'market_regime': market_regime,
                    'bb_middle': bb_middle,
                    'kc_middle': kc_middle,
                    'atr': atr
                }
            else:
                return {'action': 'hold', 'reason': '无合适交易机会'}
                
        except Exception as e:
            self.logger.error(f"计算网格信号错误: {e}")
            return {'action': 'error', 'reason': f'策略错误: {str(e)}'}
    
    def run_strategy(self, symbol: str, data: Dict) -> Dict:
        """
        运行智能网格策略
        data应包含: high, low, close, volume等OHLCV数据
        """
        try:
            if not data or 'close' not in data:
                return {'action': 'hold', 'reason': '数据不足'}
            
            # 确保数据是列表格式
            close_list = data['close']
            high_list = data.get('high', close_list)
            low_list = data.get('low', close_list)
            
            # 创建pandas Series，使用默认索引
            close_series = pd.Series(close_list)
            high_series = pd.Series(high_list)
            low_series = pd.Series(low_list)
            
            current_price = close_series.iloc[-1]
            
            # 只对BTC和ETH运行网格策略
            if not any(asset in symbol for asset in ['BTC', 'ETH']):
                return {'action': 'hold', 'reason': f'{symbol} 非BTC/ETH，不适用网格策略'}
            
            # 运行网格策略
            signal = self.calculate_grid_signal(symbol, current_price, high_series, low_series, close_series)
            
            # 转换为标准信号格式
            if signal['action'] == 'execute':
                # 选择第一个动作作为主要信号
                primary_action = signal['actions'][0]
                if primary_action['action'] == 'open_long':
                    return {
                        'side': 'long',
                        'strategy': 'smart_grid',
                        'price': current_price,
                        'size': primary_action['size'],
                        'market_regime': signal.get('market_regime', 'sideways')
                    }
                elif primary_action['action'] == 'open_short':
                    return {
                        'side': 'short', 
                        'strategy': 'smart_grid',
                        'price': current_price,
                        'size': primary_action['size'],
                        'market_regime': signal.get('market_regime', 'sideways')
                    }
                else:
                    return {'action': 'hold', 'reason': '网格管理操作'}
            
            return signal
            
        except Exception as e:
            self.logger.error(f"运行网格策略错误: {e}")
            return {'action': 'error', 'reason': f'策略执行错误: {str(e)}'}

# 策略实例
smart_grid_strategy = SmartGridStrategy()