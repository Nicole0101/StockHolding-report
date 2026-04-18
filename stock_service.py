import pandas as pd
from data_sources import get_stock_data, get_revenue_raw, get_per_pbr_90d_stats
from financial_analysis import (
    calc_eps_score,
    calc_margin_score,
    calc_trend_score,
    extract_metric,
    get_dividend_yield,
    get_eps_analysis,
    get_profit_ratio,
)
from signals import get_tech_signal
from technical_indicators import add_indicators, get_kd_trend, get_bb_trend, get_MABias
import numpy as np


def get_price_90d_high_low(df):
    df_90 = df.tail(90)

    max_price = pd.to_numeric(df_90["max"], errors="coerce").max()
    min_price = pd.to_numeric(df_90["min"], errors="coerce").min()

    if pd.isna(max_price) or pd.isna(min_price):
        return {
            "price_90d_high": None,
            "price_90d_low": None,
        }

    return {
        "price_90d_high": float(max_price),
        "price_90d_low": float(min_price),
    }


def get_revenue_trend(stock_id):
    try:
        data = get_revenue_raw(stock_id)
        if not data:
            return None

        df = pd.DataFrame(data)

        if 'revenue' not in df.columns:
            if 'value' in df.columns:
                df['revenue'] = df['value']
            else:
                return None

        df['date'] = pd.to_datetime(df['date'])
        df['revenue'] = pd.to_numeric(df['revenue'], errors='coerce')
        df = df.sort_values('date').dropna()

        if len(df) < 13:
            return None

        curr = df.iloc[-1]['revenue']
        prev_m = df.iloc[-2]['revenue']
        prev_q = df.iloc[-4]['revenue']
        prev_y = df.iloc[-13]['revenue']

        def pct(a, b):
            return (a - b) / b * 100 if b else None

        return {
            "rev": round(curr / 1e8, 2),   # 👉 bn
            "mom": round(pct(curr, prev_m), 2),
            "qoq": round(pct(curr, prev_q), 2),
            "yoy": round(pct(curr, prev_y), 2),
        }

    except Exception as e:
        print(f"❌ revenue error {stock_id}: {e}")
        return None


PER_PBR_CACHE = {}


def get_per_pbr_cached(stock_id):
    if stock_id not in PER_PBR_CACHE:
        if len(PER_PBR_CACHE) > 500:  # 限制大小
            PER_PBR_CACHE.clear()
        PER_PBR_CACHE[stock_id] = get_per_pbr_90d_stats(stock_id)
    return PER_PBR_CACHE[stock_id]


def process_stock(s):
    try:
        df = get_stock_data(s['stock_id'])
        if df.empty or len(df) < 90:
            return None

        df = add_indicators(df)
        latest, prev = df.iloc[-1], df.iloc[-2]
        price_stats = get_price_90d_high_low(df)

        chg = latest['close'] - prev['close']
        chgPct = round((chg / prev['close']) * 100, 2)
        chgamp = latest['max'] - latest['min']
        amp = round((chgamp / prev['close']) * 100, 2)

        eps_res = get_eps_analysis(s['stock_id'], latest['close'])
        eps_res = tuple(eps_res) if isinstance(eps_res, tuple) else (None,) * 6
        eps_res = eps_res + (None,) * (6 - len(eps_res))

        rev = get_revenue_trend(s['stock_id']) or {}
        profit_res = get_profit_ratio(s['stock_id']) or {
            'current': {},
            'qoq': {},
            'yoy_diff': {},
        }

        cur_g, qoq_g, yoy_g = extract_metric(profit_res, 'gross')
        cur_o, qoq_o, yoy_o = extract_metric(profit_res, 'op')
        cur_n, qoq_n, yoy_n = extract_metric(profit_res, 'net')

        yield_raw = get_dividend_yield(s['stock_id'], latest['close'])
        dividend = None
        yield_value = None
        if isinstance(yield_raw, dict):
            dividend = yield_raw.get('dividend')
            yield_value = yield_raw.get('yield')
        elif isinstance(yield_raw, (int, float)):
            yield_value = float(yield_raw)

        per_pbr_stats = get_per_pbr_cached(s['stock_id']) or {}
        ma_stats = get_MABias(df)

        safe_ma_stats = {}
        for k2, v2 in ma_stats.items():
            if v2 is None or pd.isna(v2):
                safe_ma_stats[k2] = None
            else:
                safe_ma_stats[k2] = float(v2)

        k = float(latest['K']) if pd.notna(latest['K']) else None
        d = float(latest['D']) if pd.notna(latest['D']) else None

        prev_k = float(prev['K']) if pd.notna(prev['K']) else None
        prev_d = float(prev['D']) if pd.notna(prev['D']) else None

        # KD score（統一趨勢數值）
        kd_score = 0
        if k > d and prev_k <= prev_d:
            kd_score = 1   # 黃金交叉
        elif k < d and prev_k >= prev_d:
            kd_score = -1  # 死亡交叉
        elif k > d:
            kd_score = 0.5  # 多頭但未交叉
        elif k < d:
            kd_score = -0.5  # 空頭但未交叉

        if k is None or prev_k is None:
            k_trend = None
        else:
            k_trend = 1 if k > prev_k else -1 if k < prev_k else 0

        if d is None or prev_d is None:
            d_trend = None
        else:
            d_trend = 1 if d > prev_d else -1 if d < prev_d else 0

        kd_trend = get_kd_trend(df) or {"kd_3d_up": None, "kd_trend": None}
        bb_trend = get_bb_trend(df) or {"bb_3d_up": None, "bb_trend": None}

        ma18 = latest['MA18'] if pd.notna(latest['MA18']) else None
        prev_ma18 = prev['MA18'] if pd.notna(prev['MA18']) else None

        close = latest['close']
        prev_close = prev['close']

        volume = latest.get('volume', None)
        prev_volume = prev.get('volume', None)
        volume_ratio = None
        volume_add = None
        volume_ok = False

        if pd.notna(volume) and pd.notna(prev_volume) and prev_volume > 0:
            volume_ratio = round((volume / prev_volume - 1) * 100, 2)
            volume_add = int(volume - prev_volume)
            volume_ok = bool((volume >= prev_volume * 1.1)
                             or ((volume - prev_volume) >= 500))

        bb_upper = latest['BB_upper'] if 'BB_upper' in latest else None
        bb_lower = latest['BB_lower'] if 'BB_lower' in latest else None
        bb_pct = None
        if pd.notna(bb_upper) and pd.notna(bb_lower) and bb_upper != bb_lower:
            bb_pct = round((close - bb_lower) / (bb_upper - bb_lower) * 100, 1)
            bb_pct = float(bb_pct) if bb_pct is not None else None

        bias6 = safe_ma_stats.get('bias6')
        bias18 = safe_ma_stats.get('bias18')
        bias50 = safe_ma_stats.get('bias50')
        bias6_min = safe_ma_stats.get('bias6_min')
        bias6_max = safe_ma_stats.get('bias6_max')
        bias18_min = safe_ma_stats.get('bias18_min')
        bias18_max = safe_ma_stats.get('bias18_max')
        bias50_min = safe_ma_stats.get('bias50_min')
        bias50_max = safe_ma_stats.get('bias50_max')

        signal_res = get_tech_signal(
            close=close,
            chgPct=chgPct,
            amp=amp,
            volume_ok=volume_ok,
            k=k,
            d=d,
            prev_k=prev_k,
            prev_d=prev_d,
            k_trend=k_trend,
            d_trend=d_trend,
            bb_pct=bb_pct,
            bias6=bias6,
            bias18=bias18,
            bias50=bias50,
            bias6_min=bias6_min,
            bias6_max=bias6_max,
            bias18_min=bias18_min,
            bias18_max=bias18_max,
            bias50_min=bias50_min,
            bias50_max=bias50_max,
            ma18=ma18,
            prev_ma18=prev_ma18,
            prev_close=prev_close,
        )

        signal_result = signal_res['signal_result']
        strategy = signal_res['strategy']
        reason = signal_res['reason']
        signal_text = signal_res['signal_text']

        if signal_result == '買進訊號':
            sig = 1
        elif signal_result == '賣出訊號':
            sig = -1
        else:
            sig = 0

        if None in (k, d, prev_k, prev_d):
            kd_buy = False
        else:
            kd_buy = bool((prev_k <= prev_d) and (k > d))

        ma18_break = bool(
            ma18 is not None and prev_ma18 is not None and prev_close <= prev_ma18 and close > ma18
        )

        entry_note = ''
        if '短線過熱' in reason or '不宜追價' in reason:
            entry_note = '不追價'
        elif strategy == '買入' and kd_buy and ma18_break and k < 35:
            entry_note = '抄底'
        elif strategy == '買入' and ma18_break and chgPct >= 3:
            entry_note = '追漲'

        margin_score = calc_margin_score(cur_g, cur_o, cur_n)
        eps_score = calc_eps_score(eps_res[1], eps_res[2])
        trend_score = calc_trend_score(qoq_g, yoy_g, qoq_n, yoy_n)
        score = round(margin_score * 0.4 + eps_score *
                      0.3 + trend_score * 0.3, 2)

        def to_py(v):

            if isinstance(v, (np.bool_,)):
                return bool(v)

            if isinstance(v, (np.integer,)):
                return int(v)

            if isinstance(v, (np.floating,)):
                return float(v)

            if pd.isna(v):
                return None

            return v

        result = {
            'name': s['name'],
            'code': s['stock_id'],
            'price': float(round(close, 2)),
            'price_90d_high': price_stats.get('price_90d_high'),
            'price_90d_low': price_stats.get('price_90d_low'),
            'chg': float(round(chg, 2)),
            'chgPct': float(chgPct),
            'amp': float(amp),
            "rev": rev.get("rev"),
            "rev_mom": rev.get("mom"),
            "rev_qoq": rev.get("qoq"),
            "rev_yoy": rev.get("yoy"),

            'gross_margin': float(cur_g) if cur_g is not None else None,
            'gross_margin_qoq': float(qoq_g) if qoq_g is not None else None,
            'gross_margin_yoy_diff': float(yoy_g) if yoy_g is not None else None,

            'operating_margin': float(cur_o) if cur_o is not None else None,
            'operating_margin_qoq': float(qoq_o) if qoq_o is not None else None,
            'operating_margin_yoy_diff': float(yoy_o) if yoy_o is not None else None,

            'net_margin': float(cur_n) if cur_n is not None else None,
            'net_margin_qoq': float(qoq_n) if qoq_n is not None else None,
            'net_margin_yoy_diff': float(yoy_n) if yoy_n is not None else None,

            'eps_Y': float(eps_res[0]) if eps_res[0] is not None else None,
            'eps_ttm': float(eps_res[1]) if eps_res[1] is not None else None,
            'eps_est': float(eps_res[2]) if eps_res[2] is not None else None,

            'dividend': float(dividend) if dividend is not None else None,
            'yield_value': float(yield_value) if yield_value is not None and not pd.isna(yield_value) else None,

            'per_Y': float(eps_res[3]) if eps_res[3] is not None else None,
            'per_latest': per_pbr_stats.get('per'),
            'per_90d_high': per_pbr_stats.get('per_90d_high'),
            'per_90d_low': per_pbr_stats.get('per_90d_low'),

            'pbr_latest': per_pbr_stats.get('pbr'),
            'pbr_90d_high': per_pbr_stats.get('pbr_90d_high'),
            'pbr_90d_low': per_pbr_stats.get('pbr_90d_low'),

            'k': float(round(k, 1)) if k is not None else None,
            'd': float(round(d, 1)) if d is not None else None,
            "kd_3d_up": kd_trend["kd_3d_up"],
            "kd_trend": kd_trend["kd_trend"],
            "k_trend": k_trend,
            "d_trend": d_trend,
            'kd_score': float(kd_score),
            'ma18': float(round(ma18, 2)) if ma18 is not None else None,
            'ma18_break': bool(ma18_break),
            'kd_buy': bool(kd_buy),
            'bb_pct': float(bb_pct) if bb_pct is not None else None,
            'bb_upper': float(round(bb_upper, 2)) if bb_upper is not None and pd.notna(bb_upper) else None,
            'bb_lower': float(round(bb_lower, 2)) if bb_lower is not None and pd.notna(bb_lower) else None,
            "bb_3d_up": bb_trend.get("bb_3d_up"),
            "bb_trend": bb_trend.get("bb_trend"),
            "bb_score": bb_trend.get("bb_score"),
            'volume': int(round(volume, 0)) if pd.notna(volume) else None,
            'prev_volume': int(round(prev_volume, 0)) if pd.notna(prev_volume) else None,
            'volume_ratio': float(volume_ratio) if volume_ratio is not None else None,
            'volume_add': volume_add if volume_add is not None else None,
            'volume_ok': bool(volume_ok),

            **safe_ma_stats,

            'sig': int(sig),
            'signal_result': signal_result,
            'score': float(score),
            'strategy': strategy,
            'signal_text': signal_text,
            'reason': reason,
            'entry_note': entry_note,
        }
        result = {k: to_py(v) for k, v in result.items()}
        return result
    except Exception as e:
        print(f"❌ process error {s['stock_id']}: {e}")
        return None


def get_full_stock_analysis(stock_list):
    results = []
    for s in stock_list:
        data = process_stock(s)
        if data:
            results.append(data)
    return results
