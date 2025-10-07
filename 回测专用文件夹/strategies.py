# -*- coding: utf-8 -*-
# 通用策略库：指标 + 6种策略信号函数
from typing import Dict, Any, Tuple
import pandas as pd
import numpy as np

# ========= 指标 =========
def _to_series(x: pd.Series) -> pd.Series:
    return x if isinstance(x, pd.Series) else pd.Series(x)

def sma(series: pd.Series, window: int) -> pd.Series:
    s = _to_series(series).astype(float)
    return s.rolling(window=window, min_periods=window).mean()

def ema(series: pd.Series, span: int) -> pd.Series:
    s = _to_series(series).astype(float)
    return s.ewm(span=span, adjust=False, min_periods=span).mean()

def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    s = _to_series(series).astype(float)
    fast_ema = ema(s, fast)
    slow_ema = ema(s, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    s = _to_series(series).astype(float)
    delta = s.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean().replace(0.0, np.nan)
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    s = _to_series(series).astype(float)
    mid = sma(s, period)
    std = s.rolling(window=period, min_periods=period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return upper, mid, lower

def stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k_period: int = 14, d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
    h = _to_series(high).astype(float)
    l = _to_series(low).astype(float)
    c = _to_series(close).astype(float)
    lowest_low = l.rolling(window=k_period, min_periods=k_period).min()
    highest_high = h.rolling(window=k_period, min_periods=k_period).max()
    denom = (highest_high - lowest_low).replace(0.0, np.nan)
    k = (c - lowest_low) / denom * 100.0
    d = k.rolling(window=d_period, min_periods=d_period).mean()
    return k, d

def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    h = _to_series(high).astype(float)
    l = _to_series(low).astype(float)
    c = _to_series(close).astype(float)
    prev_close = c.shift(1)
    tr1 = (h - l).abs()
    tr2 = (h - prev_close).abs()
    tr3 = (l - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()

def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    h = _to_series(high).astype(float)
    l = _to_series(low).astype(float)
    c = _to_series(close).astype(float)
    up_move = h.diff()
    down_move = -l.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=h.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=h.index)
    trv = atr(h, l, c, period).replace(0.0, np.nan)
    plus_di = 100.0 * (plus_dm.rolling(period, min_periods=period).mean() / trv)
    minus_di = 100.0 * (minus_dm.rolling(period, min_periods=period).mean() / trv)
    denom = (plus_di + minus_di).replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / denom
    return dx.rolling(window=period, min_periods=period).mean()

def _ensure_bool(d: Dict[str, pd.Series], index) -> Dict[str, pd.Series]:
    out = {}
    for k in ['long_entry','long_exit','short_entry','short_exit']:
        v = d.get(k, pd.Series(False, index=index))
        out[k] = _to_series(v).reindex(index).fillna(False).astype(bool)
    return out

# ========= 六种策略 =========
def generate_signals_trend_ema_adx_rsi(df: pd.DataFrame, cfg: Dict[str, Any] = None) -> Dict[str, pd.Series]:
    cfg = cfg or {}
    ef = ema(df['close'], int(cfg.get('ema_fast', 20)))
    es = ema(df['close'], int(cfg.get('ema_slow', 50)))
    a = adx(df['high'], df['low'], df['close'], int(cfg.get('adx_period', 14)))
    r = rsi(df['close'], int(cfg.get('rsi_period', 14)))
    trend_up = (ef > es) & (a > float(cfg.get('adx_thr', 25)))
    trend_down = (ef < es) & (a > float(cfg.get('adx_thr', 25)))
    long_entry = trend_up & (r > float(cfg.get('rsi_buy', 55)))
    long_exit = (ef < es) | (r < 50)
    short_entry = trend_down & (r < float(cfg.get('rsi_sell', 45)))
    short_exit = (ef > es) | (r > 50)
    return _ensure_bool({'long_entry': long_entry,'long_exit': long_exit,'short_entry': short_entry,'short_exit': short_exit}, df.index)

def generate_signals_macd_rsi(df: pd.DataFrame, cfg: Dict[str, Any] = None) -> Dict[str, pd.Series]:
    cfg = cfg or {}
    macd_line, signal_line, _ = macd(df['close'], int(cfg.get('macd_fast', 12)), int(cfg.get('macd_slow', 26)), int(cfg.get('macd_signal', 9)))
    r = rsi(df['close'], int(cfg.get('rsi_period', 14)))
    golden = (macd_line > signal_line) & (macd_line.shift(1) <= signal_line.shift(1))
    death = (macd_line < signal_line) & (macd_line.shift(1) >= signal_line.shift(1))
    long_entry = golden & (r > 50); long_exit = death | (r < 45)
    short_entry = death & (r < 50); short_exit = golden | (r > 55)
    return _ensure_bool({'long_entry': long_entry,'long_exit': long_exit,'short_entry': short_entry,'short_exit': short_exit}, df.index)

def generate_signals_bb_rsi(df: pd.DataFrame, cfg: Dict[str, Any] = None) -> Dict[str, pd.Series]:
    cfg = cfg or {}
    bb_u, bb_m, bb_l = bollinger_bands(df['close'], int(cfg.get('bb_period', 20)), float(cfg.get('bb_std', 2.0)))
    r = rsi(df['close'], int(cfg.get('rsi_period', 14)))
    long_entry = (df['close'] <= bb_l) & (r.shift(1) <= 30) & (r > 30)
    long_exit = (df['close'] >= bb_m) | (r < 50)
    short_entry = (df['close'] >= bb_u) & (r.shift(1) >= 70) & (r < 70)
    short_exit = (df['close'] <= bb_m) | (r > 50)
    return _ensure_bool({'long_entry': long_entry,'long_exit': long_exit,'short_entry': short_entry,'short_exit': short_exit}, df.index)

def generate_signals_kdj_ma_volume(df: pd.DataFrame, cfg: Dict[str, Any] = None) -> Dict[str, pd.Series]:
    cfg = cfg or {}
    k, d = stochastic(df['high'], df['low'], df['close'], int(cfg.get('k_period', 14)), int(cfg.get('d_period', 3)))
    ma = sma(df['close'], int(cfg.get('ma_period', 50)))
    vol_ma = sma(df['volume'], 20)
    k_up = (k > d) & (k.shift(1) <= d.shift(1)); k_dn = (k < d) & (k.shift(1) >= d.shift(1))
    strong_vol = df['volume'] > (vol_ma * float(cfg.get('vol_mult', 1.2)))
    long_entry = k_up & (df['close'] > ma) & strong_vol
    long_exit = k_dn | (df['close'] < ma)
    short_entry = k_dn & (df['close'] < ma) & strong_vol
    short_exit = k_up | (df['close'] > ma)
    return _ensure_bool({'long_entry': long_entry,'long_exit': long_exit,'short_entry': short_entry,'short_exit': short_exit}, df.index)

def generate_signals_atr_breakout(df: pd.DataFrame, cfg: Dict[str, Any] = None) -> Dict[str, pd.Series]:
    cfg = cfg or {}
    mid = sma(df['close'], int(cfg.get('ma_period', 20)))
    a = atr(df['high'], df['low'], df['close'], int(cfg.get('atr_period', 14)))
    k = float(cfg.get('k', 1.5))
    upper = mid + k * a; lower = mid - k * a
    long_entry = df['close'] > upper
    long_exit = (df['close'] < mid) | (df['close'] < lower)
    short_entry = df['close'] < lower
    short_exit = (df['close'] > mid) | (df['close'] > upper)
    return _ensure_bool({'long_entry': long_entry,'long_exit': long_exit,'short_entry': short_entry,'short_exit': short_exit}, df.index)

def generate_signals_trend_pullback_bb_rsi(df: pd.DataFrame, cfg: Dict[str, Any] = None) -> Dict[str, pd.Series]:
    cfg = cfg or {}
    ef = ema(df['close'], int(cfg.get('ema_fast', 20))); es = ema(df['close'], int(cfg.get('ema_slow', 50)))
    bb_u, bb_m, bb_l = bollinger_bands(df['close'], int(cfg.get('bb_period', 20)), float(cfg.get('bb_std', 2.0)))
    r = rsi(df['close'], int(cfg.get('rsi_period', 14)))
    rsi_lo, rsi_hi = float(cfg.get('rsi_lo', 40.0)), float(cfg.get('rsi_hi', 55.0))
    rsi_lo_s, rsi_hi_s = float(cfg.get('rsi_lo_s', 45.0)), float(cfg.get('rsi_hi_s', 60.0))
    long_entry = (ef > es) & (df['close'] <= (bb_m * 1.005)) & (r.between(rsi_lo, rsi_hi, inclusive='both'))
    long_exit = (ef < es) | (r < rsi_lo) | (df['close'] < bb_l)
    short_entry = (ef < es) & (df['close'] >= (bb_m * 0.995)) & (r.between(rsi_lo_s, rsi_hi_s, inclusive='both'))
    short_exit = (ef > es) | (r > rsi_hi_s) | (df['close'] > bb_u)
    return _ensure_bool({'long_entry': long_entry,'long_exit': long_exit,'short_entry': short_entry,'short_exit': short_exit}, df.index)