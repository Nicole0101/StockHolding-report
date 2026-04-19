from datetime import datetime

import pandas as pd

from data_sources import get_dividend_raw, get_eps_raw, get_per_raw, get_profit_ratio as get_profit_ratio_raw


def safe_margin(num, denom):
    if num is None or denom is None or denom <= 0:
        return None
    return round(num / denom * 100, 2)


def calc_diff(a, b):
    if a is None or b is None:
        return None
    return round(a - b, 2)


def fmt(v):
    return '-' if v is None else v


def build_output(result):
    cur = result['current']
    prev = result['prev']
    yoy = result['yoy']
    qoq = result['qoq']
    yoy_diff = result['yoy_diff']

    return {
        'gross_margin': cur['gross'],
        'gross_margin_prev': prev['gross'],
        'gross_margin_yoy': yoy['gross'],
        'gross_margin_qoq': qoq['gross'],
        'gross_margin_yoy_diff': yoy_diff['gross'],
        'gross_margin_combined': f"{fmt(cur['gross'])} / {fmt(prev['gross'])} / {fmt(yoy['gross'])}",
        'operating_margin': cur['op'],
        'operating_margin_prev': prev['op'],
        'operating_margin_yoy': yoy['op'],
        'operating_margin_qoq': qoq['op'],
        'operating_margin_yoy_diff': yoy_diff['op'],
        'operating_margin_combined': f"{fmt(cur['op'])} / {fmt(prev['op'])} / {fmt(yoy['op'])}",
        'net_margin': cur['net'],
        'net_margin_prev': prev['net'],
        'net_margin_yoy': yoy['net'],
        'net_margin_qoq': qoq['net'],
        'net_margin_yoy_diff': yoy_diff['net'],
        'net_margin_combined': f"{fmt(cur['net'])} / {fmt(prev['net'])} / {fmt(yoy['net'])}",
    }


def get_profit_ratio(stock_id):
    try:
        df = get_profit_ratio_raw(stock_id)
        if df.empty:
            return None

        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')

        pivot = df.pivot_table(
            index='date',
            columns='type',
            values='value',
            aggfunc='last',
        ).sort_index()

        cols = ['Revenue', 'GrossProfit',
                'OperatingIncome', 'IncomeAfterTaxes']
        missing_cols = [c for c in cols if c not in pivot.columns]
        if missing_cols:
            return None

        pivot = pivot[cols].dropna()
        if len(pivot) < 5:
            return None

        current = pivot.iloc[-1]
        prev = pivot.iloc[-2]
        yoy = pivot.iloc[-5]

        def calc(row):
            return {
                'gross': safe_margin(row['GrossProfit'], row['Revenue']),
                'op': safe_margin(row['OperatingIncome'], row['Revenue']),
                'net': safe_margin(row['IncomeAfterTaxes'], row['Revenue']),
            }

        cur_m = calc(current)
        prev_m = calc(prev)
        yoy_m = calc(yoy)

        return {
            'current': cur_m,
            'prev': prev_m,
            'yoy': yoy_m,
            'qoq': {
                'gross': calc_diff(cur_m['gross'], prev_m['gross']),
                'op': calc_diff(cur_m['op'], prev_m['op']),
                'net': calc_diff(cur_m['net'], prev_m['net']),
            },
            'yoy_diff': {
                'gross': calc_diff(cur_m['gross'], yoy_m['gross']),
                'op': calc_diff(cur_m['op'], yoy_m['op']),
                'net': calc_diff(cur_m['net'], yoy_m['net']),
            },
        }
    except Exception as e:
        print(f'❌ profit error {stock_id}: {e}')
        return None


def extract_metric(res, key):
    if not res:
        return None, None, None
    return (
        res['current'].get(key),
        res['qoq'].get(key),
        res['yoy_diff'].get(key),
    )


def get_eps_analysis(stock_id, current_price):
    try:
        data = get_eps_raw(stock_id)
        if not data:
            return (None,) * 6

        df = pd.DataFrame(data)
        df = df[df['type'] == 'EPS']
        if df.empty:
            return (None,) * 6

        df['date'] = pd.to_datetime(df['date'])
        df['year'] = df['date'].dt.year
        df['season'] = df['date'].dt.quarter
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        df = df.sort_values('date').drop_duplicates(
            ['year', 'season'], keep='last')

        last_year = datetime.now().year - 1
        df_last = df[df['year'] == last_year]

        eps_last = None
        if df_last['season'].nunique() >= 4:
            eps_last = round(df_last['value'].sum(), 2)

        df_ttm = df.sort_values('date').tail(4)
        eps_ttm = round(df_ttm['value'].sum(), 2) if len(df_ttm) == 4 else None

        yearly_eps = df.groupby('year')['value'].sum().sort_index()
        eps_est = None
        if len(yearly_eps) >= 3:
            last_3 = yearly_eps.tail(3)
            start = last_3.iloc[0]
            end = last_3.iloc[-1]
            years = len(last_3) - 1
            if start > 0 and end > 0 and years > 0:
                cagr = (end / start) ** (1 / years) - 1
                eps_est = round(end * (1 + cagr), 2)
            else:
                eps_est = None


        def calc_per(price, eps):
            return round(price / eps, 2) if eps and eps > 0 else None

        per_last = calc_per(current_price, eps_last)
        per_ttm = calc_per(current_price, eps_ttm)
        per_est = calc_per(current_price, eps_est)

        return eps_last, eps_ttm, eps_est, per_last, per_ttm, per_est
    except Exception as e:
        print(f'❌ EPS error {stock_id}: {e}')
        return (None,) * 6


def get_dividend_yield(stock_id, current_price=None):
    try:
        data = get_dividend_raw(stock_id)
        if not data:
            return {'dividend': None, 'yield': None}

        df = pd.DataFrame(data)
        cash_cols = ['CashEarningsDistribution', 'CashStatutorySurplus']
        exist_cols = [c for c in cash_cols if c in df.columns]
        if not exist_cols:
            return {'dividend': None, 'yield': None}

        df[exist_cols] = df[exist_cols].apply(pd.to_numeric, errors='coerce')
        df['year'] = pd.to_numeric(df['year'], errors='coerce')

        df_group = (
            df.groupby('year')[exist_cols]
            .sum()
            .sum(axis=1)
            .reset_index(name='cash_dividend')
            .sort_values('year', ascending=False)
        )

        dividend = None
        for val in df_group['cash_dividend']:
            if val and val > 0:
                dividend = round(val, 2)
                break

        yield_pct = None
        per_data = get_per_raw(stock_id)
        if per_data:
            df2 = pd.DataFrame(per_data)
            df2['date'] = pd.to_datetime(df2['date'])
            latest = df2.sort_values('date').iloc[-1]
            yield_pct = latest.get('dividend_yield')
            if yield_pct is not None:
                yield_pct = round(float(yield_pct), 2)

        if yield_pct is None and dividend and current_price and current_price > 0:
            yield_pct = round(dividend / current_price * 100, 2)

        return {'dividend': dividend, 'yield': yield_pct}
    except Exception as e:
        print(f'❌ 股利/殖利率錯誤 {stock_id}: {e}')
        return {'dividend': None, 'yield': None}


def calc_margin_score(gross, op, net):
    score = 0
    if gross is not None:
        score += gross * 0.4
    if op is not None:
        score += op * 0.3
    if net is not None:
        score += net * 0.3
    return round(score, 2)


def calc_eps_score(eps_ttm, eps_est):
    if eps_ttm is None or eps_est is None or eps_ttm <= 0:
        return 0
    growth = (eps_est - eps_ttm) / eps_ttm * 100
    return round(growth, 2)


def calc_trend_score(qoq_g, yoy_g, qoq_n, yoy_n):
    vals = [qoq_g, yoy_g, qoq_n, yoy_n]
    vals = [v for v in vals if v is not None]
    if not vals:
        return 0
    return round(sum(vals) / len(vals), 2)
