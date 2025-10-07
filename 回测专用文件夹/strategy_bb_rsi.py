# -*- coding: utf-8 -*-
from typing import Dict, Any, Optional
import pandas as pd
from strategies import generate_signals_bb_rsi as _impl

def generate_signals(df: pd.DataFrame, cfg: Optional[Dict[str, Any]] = None):
    return _impl(df, cfg or {})