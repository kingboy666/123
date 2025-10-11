#!/usr/bin/env python3
# main_bot.py
# Merged K-line Momentum + ATR adaptive SL/TP robot using exchange-side conditional orders
# Multi-symbol per-symbol timeframe, leverage, ATR params, dynamic trailing, stats
#
# Usage:
#   Set env vars: OKX_API_KEY, OKX_API_SECRET, OKX_API_PASSPHRASE
#   Optionally SANDBOX=true for sandbox mode
#   python main_bot.py

import os
import time
import math
import logging
import traceback
from datetime import datetime
from collections import defaultdict, deque

import ccxt
import pandas as pd
import numpy as np

# -------------------------
# Logging
# -------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logger = logging.getLogger("main_kmomentum")
logger.setLevel(LOG_LEVEL)
h = logging.StreamHandler()
h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(h)

# -------------------------
# General configuration
# -------------------------
SANDBOX = os.getenv("SANDBOX", "false").lower() in ("1", "true", "yes")
OKX_API_KEY = os.getenv("OKX_API_KEY")
OKX_API_SECRET = os.getenv("OKX_API_SECRET") or os.getenv("OKX_SECRET_KEY")
OKX_API_PASSPHRASE = os.getenv("OKX_API_PASSPHRASE") or os.getenv("OKX_PASSPHRASE")

if not (OKX_API_KEY and OKX_API_SECRET and OKX_API_PASSPHRASE):
    logger.warning("OKX API credentials not fully provided in env. Please set OKX_API_KEY/OKX_API_SECRET/OKX_API_PASSPHRASE.")

# per-symbol configuration (timeframe, leverage, atr_sl_mult, atr_tp_mult, trailing thresholds)
# You can edit these per your preference.
SYMBOL_CONFIG = {
    'FIL/USDT:USDT':  {'tf':'15m','lev':30,'atr_sl':2.2,'atr_tp':4.4,'trail':[1.5,2.0,2.5]},
    'ZRO/USDT:USDT':  {'tf':'5m', 'lev':30,'atr_sl':2.5,'atr_tp':5.0,'trail':[1.5,2.0,2.5]},
    'WIF/USDT:USDT':  {'tf':'5m', 'lev':30,'atr_sl':2.5,'atr_tp':5.0,'trail':[1.5,2.0,2.5]},
    'WLD/USDT:USDT':  {'tf':'15m','lev':25,'atr_sl':2.5,'atr_tp':5.0,'trail':[1.5,2.0,2.5]},
    'BTC/USDT:USDT':  {'tf':'15m','lev':25,'atr_sl':1.5,'atr_tp':3.0,'trail':[1.5,2.0,2.5]},
    'ETH/USDT:USDT':  {'tf':'15m','lev':25,'atr_sl':1.6,'atr_tp':3.2,'trail':[1.5,2.0,2.5]},
    'SOL/USDT:USDT':  {'tf':'15m','lev':30,'atr_sl':1.8,'atr_tp':3.6,'trail':[1.5,2.0,2.5]},
    'DOGE/USDT:USDT': {'tf':'5m', 'lev':40,'atr_sl':2.0,'atr_tp':4.0,'trail':[1.5,2.0,2.5]},
    'XRP/USDT:USDT':  {'tf':'15m','lev':25,'atr_sl':1.7,'atr_tp':3.4,'trail':[1.5,2.0,2.5]},
    'PEPE/USDT:USDT': {'tf':'5m', 'lev':30,'atr_sl':2.8,'atr_tp':5.6,'trail':[1.5,2.0,2.5]},
    'ARB/USDT:USDT':  {'tf':'15m','lev':30,'atr_sl':2.0,'atr_tp':4.0,'trail':[1.5,2.0,2.5]},
}

GLOBAL_TIMEFRAME = "15m"
ATR_PERIOD = int(os.getenv("ATR_PERIOD", "14"))
BODY_RATIO_THRESHOLD = float(os.getenv("BODY_RATIO_THRESHOLD", "0.6"))
CONFIRM_CANDLES = int(os.getenv("CONFIRM_CANDLES", "2"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.01"))  # fraction of free USDT to risk per trade
MIN_ORDER_USDT = float(os.getenv("MIN_ORDER_USDT", "1.0"))
MAIN_LOOP_INTERVAL = float(os.getenv("MAIN_LOOP_INTERVAL", "10"))  # seconds between main loop iterations
BARS_LIMIT = 500
SLIPPAGE_PCT = float(os.getenv("SLIPPAGE_PCT", "0.001"))  # assumed total fees+slippage
# Protective parameters
EXTREME_VOLATILITY_THRESHOLD = float(os.getenv("EXTREME_VOLATILITY_THRESHOLD", "0.05"))  # e.g., 5%
MIN_SL_DISTANCE_PCT = float(os.getenv("MIN_SL_DISTANCE_PCT", "0.005"))  # e.g., 0.5%
LIQUIDATION_BUFFER_PCT = float(os.getenv("LIQUIDATION_BUFFER_PCT", "0.15"))  # e.g., 15%

# -------------------------
# Exchange init
# -------------------------
exchange_params = {
    'apiKey': OKX_API_KEY,
    'secret': OKX_API_SECRET,
    'password': OKX_API_PASSPHRASE,
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'},
}
exchange = ccxt.okx(exchange_params)
exchange.verbose = False

# -------------------------
# Utils: fetch OHLCV, ATR, body ratio
# -------------------------
def fetch_ohlcv(symbol, timeframe, limit=BARS_LIMIT):
    attempts = 0
    while attempts < 5:
        try:
            bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            if not bars:
                return None
            df = pd.DataFrame(bars, columns=['ts','open','high','low','close','volume'])
            df['datetime'] = pd.to_datetime(df['ts'], unit='ms')
            df.set_index('datetime', inplace=True)
            return df
        except Exception as e:
            attempts += 1
            logger.debug(f"fetch_ohlcv {symbol} err {e} attempt {attempts}")
            time.sleep(1 + attempts)
    logger.error(f"fetch_ohlcv failed {symbol}")
    return None

def compute_atr(df, period=ATR_PERIOD):
    high = df['high']; low = df['low']; close = df['close']
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return atr

def body_ratio_series(df):
    body = (df['close'] - df['open']).abs()
    rng = (df['high'] - df['low']).replace(0, 1e-9)
    return (body / rng).fillna(0)

def get_last_close(df):
    try:
        return float(df['close'].iloc[-1])
    except Exception:
        return 0.0

def is_extreme_volatility(df, atr_val, threshold=EXTREME_VOLATILITY_THRESHOLD, recent=5):
    """
    Extreme if ATR/last_close > threshold OR max((high-low)/close) over last N > threshold
    """
    try:
        last_close = get_last_close(df)
        if last_close <= 0 or atr_val <= 0:
            return False
        atr_ratio = atr_val / last_close
        seg = df.iloc[-recent:] if len(df) >= recent else df
        vol = ((seg['high'] - seg['low']) / seg['close'].replace(0, 1e-9)).clip(lower=0).max()
        return bool((atr_ratio > threshold) or (vol > threshold))
    except Exception:
        return False

def get_liquidation_price(symbol):
    """
    Best-effort: try fetch_positions to get liquidationPrice if available.
    Returns float or None if unavailable.
    """
    try:
        poss = exchange.fetch_positions([symbol])
        if isinstance(poss, list):
            for p in poss:
                if p.get('symbol') == symbol:
                    lp = p.get('liquidationPrice')
                    if lp is not None:
                        try:
                            v = float(lp)
                            return v if v > 0 else None
                        except Exception:
                            continue
        return None
    except Exception:
        return None

# -------------------------
# Position & stats storage
# -------------------------
positions = {}  # symbol -> position dict
# position fields:
# - side, entry_price, qty, sl_order_id, tp_order_id, atr_sl_value, atr_val, opened_at, trail_stage flags

stats = defaultdict(lambda: {'trades':0,'wins':0,'losses':0,'pnl':0.0,'history':[]})
equity_series = deque(maxlen=10000)

def print_portfolio_summary():
    """
    打印账户与策略摘要：总余额、总交易/胜率/累计PnL、持仓概览
    """
    try:
        # 账户余额
        balance = get_free_balance_usdt()
        # 聚合统计
        total_trades = 0
        total_wins = 0
        total_losses = 0
        total_pnl = 0.0
        for s in stats.values():
            total_trades += s.get('trades', 0)
            total_wins += s.get('wins', 0)
            total_losses += s.get('losses', 0)
            total_pnl += float(s.get('pnl', 0.0) or 0.0)
        winrate = (total_wins / total_trades * 100.0) if total_trades > 0 else 0.0
        # 摘要
        logger.info(f"SUMMARY balance={balance:.2f}U trades={total_trades} winrate={winrate:.1f}% pnl={total_pnl:.2f}U positions={len(positions)}")
        # 持仓简表
        if positions:
            for sym, pos in positions.items():
                side = pos.get('side')
                qty = float(pos.get('qty') or 0.0)
                entry = float(pos.get('entry_price') or 0.0)
                logger.info(f"POSITION {sym} side={side} qty={qty:.6f} entry={entry:.6f}")
    except Exception:
        # 避免摘要打印影响主逻辑
        pass

# -------------------------
# Account helpers
# -------------------------
def safe_float(v):
    try:
        return float(v)
    except:
        return 0.0

def get_free_balance_usdt():
    attempts = 0
    while attempts < 4:
        try:
            bal = exchange.fetch_balance(params={"type":"swap"})
            # try common fields
            if isinstance(bal, dict):
                free = bal.get('free') or {}
                if isinstance(free, dict) and 'USDT' in free:
                    return safe_float(free['USDT'])
                total = bal.get('total') or {}
                if isinstance(total, dict) and 'USDT' in total:
                    return safe_float(total['USDT'])
                info = bal.get('info') or {}
                # best-effort extraction
                data = info.get('data') or info
                if isinstance(data, list):
                    for it in data:
                        if isinstance(it, dict) and (it.get('ccy') == 'USDT' or it.get('currency')=='USDT'):
                            return safe_float(it.get('avail') or it.get('availBal') or it.get('available'))
            return 0.0
        except Exception as e:
            attempts += 1
            logger.debug(f"fetch_balance err {e} attempt {attempts}")
            time.sleep(1 + attempts)
    logger.error("Unable to fetch balance reliably")
    return 0.0

# -------------------------
# Order helpers: create entry + exchange-side conditional SL/TP
# -------------------------
def create_market_entry(symbol, side, notional_usdt, leverage):
    """
    Place market order opening a position approximately sized by notional_usdt * leverage.
    Returns dict with filled_qty and entry_price info (best-effort).
    """
    try:
        ticker = exchange.fetch_ticker(symbol)
        last = ticker.get('last') or ticker.get('close') or None
        if last and last > 0:
            qty = (notional_usdt * leverage) / last
        else:
            qty = max(1, notional_usdt * leverage)
        # try create market order
        try:
            order = exchange.create_market_order(symbol, 'buy' if side=='buy' else 'sell', qty)
        except Exception as e:
            logger.warning(f"create_market_order fallback for {symbol}: {e}")
            order = exchange.create_order(symbol, 'market', 'buy' if side=='buy' else 'sell', qty, None)
        filled_qty = safe_float(order.get('filled', 0.0) or order.get('amount', 0.0) or qty)
        entry_price = safe_float(order.get('average') or order.get('price') or last)
        if filled_qty == 0:
            filled_qty = qty
        return {'filled_qty': filled_qty, 'entry_price': entry_price, 'order': order}
    except Exception as e:
        logger.error(f"create_market_entry error {e}")
        raise

def place_conditional_order(symbol, side, amount, trigger_price, reduce_only=True, client_tag=None):
    """
    Try several common param patterns to create conditional (stop) orders on OKX via ccxt.
    Returns order response (object/dict) or None.
    """
    client_tag = client_tag or f"auto_{int(time.time()*1000)}"
    tries = []
    # Common try 1
    p1 = {'triggerPrice': float(trigger_price), 'reduceOnly': reduce_only, 'clientOrderId': client_tag}
    tries.append(p1)
    # Try 2
    p2 = {'stopPrice': float(trigger_price), 'reduceOnly': reduce_only, 'orderType': 'market', 'clientOrderId': client_tag + "_v2"}
    tries.append(p2)
    # Try 3 - closeOnTrigger
    p3 = {'triggerPrice': float(trigger_price), 'reduceOnly': reduce_only, 'closeOnTrigger': True, 'clientOrderId': client_tag + "_v3"}
    tries.append(p3)
    # Try 4 - platform-specific raw (best-effort)
    for p in tries:
        try:
            # create as market for immediate execution when triggered
            resp = exchange.create_order(symbol, type='market', side=side, amount=amount, price=None, params=p)
            return resp
        except Exception as e:
            logger.debug(f"place_conditional_order try failed for {symbol} params {p}: {e}")
            continue
    # last resort: return None
    logger.error(f"place_conditional_order all tries failed for {symbol} trigger {trigger_price}")
    return None

def cancel_order_safe(order_id, symbol):
    try:
        return exchange.cancel_order(order_id, symbol, params={})
    except Exception as e:
        logger.debug(f"cancel_order_safe error {e} for {order_id}")
        return None

# -------------------------
# K-line momentum detection
# -------------------------
def detect_kline_momentum(df, confirm=CONFIRM_CANDLES, body_thr=BODY_RATIO_THRESHOLD):
    """
    Return 'buy' or 'sell' or None.
    Uses last confirm candles: require each candle entity ratio >= body_thr and same direction,
    and final close breaks prev baseline high/low.
    """
    if len(df) < confirm + 1:
        return None
    br = body_ratio_series(df)
    last = df.iloc[-(confirm+1):].copy()  # includes 1 baseline + confirm candles
    br_last = br.iloc[-(confirm+1):]
    prev_high = last['high'].iloc[0]
    prev_low = last['low'].iloc[0]
    directions = []
    for i in range(1, confirm+1):
        row = last.iloc[i]
        brv = br_last.iloc[i]
        if row['close'] > row['open'] and brv >= body_thr:
            directions.append('bull')
        elif row['close'] < row['open'] and brv >= body_thr:
            directions.append('bear')
        else:
            directions.append('none')
    if all(d == 'bull' for d in directions):
        if last['close'].iloc[-1] > prev_high:
            return 'buy'
    if all(d == 'bear' for d in directions):
        if last['close'].iloc[-1] < prev_low:
            return 'sell'
    return None

# -------------------------
# SL/TP calc and dynamic trailing logic
# -------------------------
def calc_sl_tp_from_atr(entry_price, side, atr_val, atr_sl_mult, atr_tp_mult):
    sl_dist = atr_val * atr_sl_mult
    tp_dist = atr_val * atr_tp_mult
    if side == 'buy':
        sl_price = entry_price - sl_dist
        tp_price = entry_price + tp_dist
    else:
        sl_price = entry_price + sl_dist
        tp_price = entry_price - tp_dist
    return sl_price, tp_price, sl_dist, tp_dist

def enforce_sl_protections(symbol, side, entry_price, raw_sl):
    """
    Enforce MIN_SL_DISTANCE_PCT and LIQUIDATION_BUFFER_PCT if possible.
    Returns adjusted SL price.
    """
    try:
        min_dist = max(0.0, entry_price * MIN_SL_DISTANCE_PCT)
        if side == 'buy':
            # SL must be no higher than entry - min_dist
            sl_price = min(raw_sl, entry_price - min_dist)
            # liquidation buffer (if available)
            liq = get_liquidation_price(symbol)
            if liq and liq > 0:
                safe_min = liq * (1.0 + LIQUIDATION_BUFFER_PCT)
                # SL cannot be below this safety bound (avoid too close to liquidation)
                sl_price = max(sl_price, safe_min)
            return sl_price
        else:  # sell/short
            sl_price = max(raw_sl, entry_price + min_dist)
            liq = get_liquidation_price(symbol)
            if liq and liq > 0:
                safe_max = liq * (1.0 - LIQUIDATION_BUFFER_PCT)
                sl_price = min(sl_price, safe_max)
            return sl_price
    except Exception:
        return raw_sl

def calc_protected_sl_tp(symbol, entry_price, side, atr_val, atr_sl_mult, atr_tp_mult, df):
    """
    Calculate SL/TP with extreme-volatility shrink, min SL distance, and liquidation buffer.
    """
    # extreme volatility -> shrink SL multiple
    eff_sl_mult = atr_sl_mult
    if is_extreme_volatility(df, atr_val, threshold=EXTREME_VOLATILITY_THRESHOLD):
        eff_sl_mult = max(0.0, atr_sl_mult * 0.5)
    sl_dist = atr_val * eff_sl_mult
    tp_dist = atr_val * atr_tp_mult
    if side == 'buy':
        raw_sl = entry_price - sl_dist
        tp_price = entry_price + tp_dist
    else:
        raw_sl = entry_price + sl_dist
        tp_price = entry_price - tp_dist
    sl_price = enforce_sl_protections(symbol, side, entry_price, raw_sl)
    return sl_price, tp_price, sl_dist, tp_dist

def ensure_protective_orders(symbol, pos, df):
    """
    确保每轮循环都有保护单：
    - 若缺SL/TP中的任意一个，则计算并补挂
    - 若已存在，则跳过，不重复下单
    说明：为避免多余刷新，这里不强制重挂，仅在缺失时补齐。
    """
    try:
        side = pos.get('side')
        qty = float(pos.get('qty') or 0.0)
        entry = float(pos.get('entry_price') or 0.0)
        atr_val = float(pos.get('atr_val') or 0.0)
        cfg = pos.get('cfg') or {}
        if qty <= 0 or entry <= 0 or atr_val <= 0 or not side:
            return
        # 计算一次受保护的SL/TP价格
        sl_price, tp_price, _, _ = calc_protected_sl_tp(symbol, entry, side, atr_val, cfg.get('atr_sl', 2.0), cfg.get('atr_tp', 3.0), df)
        # 若缺SL则补
        if not pos.get('sl_order_id'):
            new_sl_order = place_conditional_order(symbol, 'sell' if side=='buy' else 'buy', qty, sl_price, reduce_only=True)
            pos['sl_order'] = new_sl_order
            pos['sl_order_id'] = (new_sl_order.get('id') if isinstance(new_sl_order, dict) else None)
            logger.info(f"{symbol} ensure SL placed at {sl_price:.6f}")
        # 若缺TP则补
        if not pos.get('tp_order_id'):
            new_tp_order = place_conditional_order(symbol, 'sell' if side=='buy' else 'buy', qty, tp_price, reduce_only=True)
            pos['tp_order'] = new_tp_order
            pos['tp_order_id'] = (new_tp_order.get('id') if isinstance(new_tp_order, dict) else None)
            logger.info(f"{symbol} ensure TP placed at {tp_price:.6f}")
    except Exception as e:
        logger.debug(f"{symbol} ensure_protective_orders error: {e}")
    """
    Calculate SL/TP with extreme-volatility shrink, min SL distance, and liquidation buffer.
    """
    # extreme volatility -> shrink SL multiple
    eff_sl_mult = atr_sl_mult
    if is_extreme_volatility(df, atr_val, threshold=EXTREME_VOLATILITY_THRESHOLD):
        eff_sl_mult = max(0.0, atr_sl_mult * 0.5)
    sl_dist = atr_val * eff_sl_mult
    tp_dist = atr_val * atr_tp_mult
    if side == 'buy':
        raw_sl = entry_price - sl_dist
        tp_price = entry_price + tp_dist
    else:
        raw_sl = entry_price + sl_dist
        tp_price = entry_price - tp_dist
    sl_price = enforce_sl_protections(symbol, side, entry_price, raw_sl)
    return sl_price, tp_price, sl_dist, tp_dist

def apply_dynamic_trailing(symbol, pos, current_price):
    """
    Check trailing stages configured in SYMBOL_CONFIG and update SL accordingly.
    pos must include entry_price, atr_val, cfg (for trail thresholds), qty, sl_order_id
    """
    try:
        cfg = pos['cfg']
        trail_thresholds = cfg.get('trail', [1.5,2.0,2.5])
        entry = pos['entry_price']
        atr = pos['atr_val']
        side = pos['side']
        qty = pos['qty']
        # compute pnl distance
        pnl_dist = (current_price - entry) if side == 'buy' else (entry - current_price)
        # stage1: >= trail[0]
        changed = False
        if (pnl_dist >= trail_thresholds[0]*atr) and not pos.get('trail_1'):
            # move SL to breakeven
            new_sl = enforce_sl_protections(symbol, side, entry, entry)
            logger.info(f"{symbol} trail stage1 triggered: move SL to breakeven {new_sl}")
            # cancel old sl order and create new conditional SL at new_sl
            try:
                if pos.get('sl_order_id'):
                    cancel_order_safe(pos.get('sl_order_id'), symbol)
                new_sl_order = place_conditional_order(symbol, 'sell' if side=='buy' else 'buy', qty, new_sl, reduce_only=True)
                pos['sl_order'] = new_sl_order
                pos['sl_order_id'] = (new_sl_order.get('id') if isinstance(new_sl_order, dict) else None)
            except Exception as e:
                logger.warning(f"{symbol} trail stage1 reorder failed: {e}")
            pos['trail_1'] = True
            changed = True
        # stage2: >= trail[1]
        if (pnl_dist >= trail_thresholds[1]*atr) and not pos.get('trail_2'):
            new_sl = entry + (1.0*atr if side=='buy' else -1.0*atr)
            new_sl = enforce_sl_protections(symbol, side, entry, new_sl)
            logger.info(f"{symbol} trail stage2 triggered: move SL to lock profit {new_sl}")
            try:
                if pos.get('sl_order_id'):
                    cancel_order_safe(pos.get('sl_order_id'), symbol)
                new_sl_order = place_conditional_order(symbol, 'sell' if side=='buy' else 'buy', qty, new_sl, reduce_only=True)
                pos['sl_order'] = new_sl_order
                pos['sl_order_id'] = (new_sl_order.get('id') if isinstance(new_sl_order, dict) else None)
            except Exception as e:
                logger.warning(f"{symbol} trail stage2 reorder failed: {e}")
            pos['trail_2'] = True
            changed = True
        # stage3: >= trail[2] -> close fully
        if (pnl_dist >= trail_thresholds[2]*atr):
            logger.info(f"{symbol} trail stage3 triggered: closing position by market")
            try:
                exchange.create_market_order(symbol, 'sell' if side=='buy' else 'buy', qty, params={'reduceOnly': True})
            except Exception as e:
                logger.error(f"{symbol} stage3 market close failed: {e}")
            # cancel any protective orders
            if pos.get('sl_order_id'):
                cancel_order_safe(pos.get('sl_order_id'), symbol)
            if pos.get('tp_order_id'):
                cancel_order_safe(pos.get('tp_order_id'), symbol)
            # finalize stats
            finalize_position_close(symbol, pos, forced=True)
            return True  # closed
        return changed
    except Exception as e:
        logger.error(f"apply_dynamic_trailing error for {symbol}: {e}")
        return False

# -------------------------
# Finalize a closed position: compute pnl & update stats
# -------------------------
def finalize_position_close(symbol, pos, forced=False):
    """
    Called when position determined to be closed. Update stats and remove from positions.
    """
    try:
        entry = pos.get('entry_price')
        side = pos.get('side')
        qty = float(pos.get('qty') or 0.0)
        # get last price
        ticker = exchange.fetch_ticker(symbol)
        last = safe_float(ticker.get('last') or ticker.get('close') or 0.0)
        if last == 0:
            logger.warning(f"{symbol} finalize unable to fetch last price; skipping pnl calc")
            pnl = 0.0
        else:
            # approximate pnl = (exit - entry) * qty * (1 - fees)
            exit_price = last
            gross = (exit_price - entry) if side=='buy' else (entry - exit_price)
            pnl = gross * qty * (1 - SLIPPAGE_PCT)
        stats[symbol]['trades'] += 1
        stats[symbol]['pnl'] += pnl
        stats[symbol]['history'].append({'time': datetime.utcnow().isoformat(),'pnl':pnl,'forced':forced})
        if pnl > 0:
            stats[symbol]['wins'] += 1
        else:
            stats[symbol]['losses'] += 1
        logger.info(f"{symbol} closed pos pnl={pnl:.4f} trades={stats[symbol]['trades']} wins={stats[symbol]['wins']}")
    except Exception as e:
        logger.error(f"finalize_position_close error {e}")
    finally:
        positions.pop(symbol, None)

# -------------------------
# Main loop
# -------------------------
def main_loop():
    logger.info("Starting main loop. SANDBOX=%s" % SANDBOX)
    while True:
        loop_start = time.time()
        try:
            free_usdt = get_free_balance_usdt()
            if free_usdt <= 0:
                logger.warning("Free USDT <= 0, sleeping 10s")
                time.sleep(10)
                continue
            # allocate per-symbol equally
            alloc = max(MIN_ORDER_USDT, free_usdt / max(1, len(SYMBOL_CONFIG)))
        except Exception as e:
            logger.error(f"balance/alloc error {e}")
            alloc = MIN_ORDER_USDT

        for symbol, cfg in SYMBOL_CONFIG.items():
            try:
                tf = cfg.get('tf') or GLOBAL_TIMEFRAME
                df = fetch_ohlcv(symbol, tf, limit=BARS_LIMIT)
                if df is None or len(df) < ATR_PERIOD + CONFIRM_CANDLES + 3:
                    logger.debug(f"{symbol} insufficient data; skip")
                    continue
                atr = compute_atr(df)
                atr_val = atr.iloc[-1]
                if not atr_val or math.isnan(atr_val) or atr_val <= 0:
                    logger.debug(f"{symbol} ATR invalid {atr_val}; skip")
                    continue
                signal = detect_kline_momentum(df, confirm=CONFIRM_CANDLES)
                pos = positions.get(symbol)
                # If position exists, process trailing and reverse-signal closure
                if pos:
                    # fetch current price
                    ticker = exchange.fetch_ticker(symbol)
                    last = safe_float(ticker.get('last') or ticker.get('close') or df['close'].iloc[-1])
                    closed = apply_dynamic_trailing(symbol, pos, last)
                    if closed:
                        continue  # position closed by trailing stage3
                    # check reverse momentum
                    if (pos['side']=='buy' and signal=='sell') or (pos['side']=='sell' and signal=='buy'):
                        logger.info(f"{symbol} reverse momentum detected -> force close market")
                        try:
                            exchange.create_market_order(symbol, 'sell' if pos['side']=='buy' else 'buy', pos['qty'], params={'reduceOnly': True})
                        except Exception as e:
                            logger.error(f"{symbol} force close error {e}")
                        # cancel protective orders
                        if pos.get('sl_order_id'):
                            cancel_order_safe(pos.get('sl_order_id'), symbol)
                        if pos.get('tp_order_id'):
                            cancel_order_safe(pos.get('tp_order_id'), symbol)
                        finalize_position_close(symbol, pos, forced=True)
                        continue
                    # ensure protective orders exist (if missing then place, otherwise skip)
                    ensure_protective_orders(symbol, pos, df)
                    # else keep monitoring
                    continue

                # No existing position; if signal exists, open
                if signal in ('buy','sell'):
                    side = signal
                    # estimate entry price
                    ticker = exchange.fetch_ticker(symbol)
                    entry_est = safe_float(ticker.get('last') or df['close'].iloc[-1])
                    # calc sl/tp with protections (extreme volatility shrink, min SL distance, liquidation buffer)
                    sl_price, tp_price, sl_dist, tp_dist = calc_protected_sl_tp(symbol, entry_est, side, atr_val, cfg['atr_sl'], cfg['atr_tp'], df)
                    # place market entry
                    try:
                        entry_res = create_market_entry(symbol, side, alloc, cfg['lev'])
                    except Exception as e:
                        logger.error(f"{symbol} entry create error: {e}")
                        continue
                    filled_qty = entry_res.get('filled_qty')
                    entry_price = entry_res.get('entry_price')
                    # place protective conditional orders on exchange
                    # stoploss order (reduceOnly) - trigger on sl_price
                    sl_order = place_conditional_order(symbol, 'sell' if side=='buy' else 'buy', filled_qty, sl_price, reduce_only=True)
                    tp_order = place_conditional_order(symbol, 'sell' if side=='buy' else 'buy', filled_qty, tp_price, reduce_only=True)
                    # record position
                    positions[symbol] = {
                        'side': side,
                        'entry_price': entry_price,
                        'qty': filled_qty,
                        'sl_order': sl_order,
                        'tp_order': tp_order,
                        'sl_order_id': (sl_order.get('id') if isinstance(sl_order, dict) else None),
                        'tp_order_id': (tp_order.get('id') if isinstance(tp_order, dict) else None),
                        'atr_sl_value': atr_val * cfg['atr_sl'],
                        'atr_val': atr_val,
                        'opened_at': datetime.utcnow().isoformat(),
                        'cfg': cfg,
                        # trailing flags
                        'trail_1': False,
                        'trail_2': False
                    }
                    logger.info(f"{symbol} OPEN {side} entry={entry_price:.6f} qty={filled_qty} sl={sl_price:.6f} tp={tp_price:.6f}")
                    # record a trade pending stat entry (actual pnl updated on close)
                    # continue to next symbol
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}\n{traceback.format_exc()}")

        # after processing symbols, print summary and sleep to next tick
        print_portfolio_summary()
        elapsed = time.time() - loop_start
        to_sleep = max(1.0, MAIN_LOOP_INTERVAL - elapsed)
        time.sleep(to_sleep)

# -------------------------
# Utility: periodic stats print
# -------------------------
def print_stats_periodically():
    while True:
        try:
            time.sleep(60)  # print every minute
            logger.info("===== PORTFOLIO STATS =====")
            total_pnl = 0.0
            for sym, s in stats.items():
                total_pnl += s['pnl']
                trades = s['trades']
                wins = s['wins']
                losses = s['losses']
                winrate = (wins / trades * 100) if trades>0 else 0.0
                logger.info(f"{sym}: trades={trades} wins={wins} losses={losses} winrate={winrate:.1f}% pnl={s['pnl']:.4f}")
            logger.info(f"TOTAL PNL (approx): {total_pnl:.4f}")
        except Exception as e:
            logger.error(f"stats print error {e}")

# -------------------------
# Main entry
# -------------------------
if __name__ == "__main__":
    try:
        logger.info("Launching merged K-line Momentum + ATR Robot")
        main_loop()
    except KeyboardInterrupt:
        logger.info("Interrupted by user, exiting.")
    except Exception as e:
        logger.error(f"Fatal error: {e}\n{traceback.format_exc()}")
