import logging
import requests
import pandas as pd
import os
from loguru import logger
from datetime import datetime
from FinMind.data import DataLoader

API_TOKEN = os.getenv("FINMIND_TOKEN")
api_url = "https://api.finmindtrade.com/api/v4/data"
api = DataLoader()

# 停用所有來自 FinMind 的 Log 訊息
logger.remove()
logging.getLogger("FinMind").setLevel(logging.WARNING)


# ========================
# 1️⃣ 價格資料
# ========================
def get_stock_data(stock_id):
    try:
        params = {
            "dataset": "TaiwanStockPrice",
            "data_id": str(stock_id),
            "start_date": "2023-01-01",
            "token": API_TOKEN,
        }
        res = requests.get(api_url, params=params, timeout=10)
        data = res.json()

        if "data" not in data or len(data["data"]) == 0:
            return pd.DataFrame()

        df = pd.DataFrame(data["data"])

        volume_col = None
        for c in ["Trading_Volume", "trading_volume", "Trading_Volume_1000"]:
            if c in df.columns:
                volume_col = c
                break

        required_cols = ["date", "open", "close", "max", "min"]
        if volume_col:
            required_cols.append(volume_col)

        df = df[required_cols].copy()
        df["date"] = pd.to_datetime(df["date"])

        if volume_col:
            df["volume"] = pd.to_numeric(df[volume_col], errors="coerce")
            if df["volume"].max() > 100000:
                df["volume"] = df["volume"] / 1000
        else:
            df["volume"] = None

        df = df.dropna(subset=["open", "close", "max", "min"]).sort_values("date")
        return df

    except Exception as e:
        print(f"❌ get_stock_data error {stock_id}: {e}")
        return pd.DataFrame()


# ========================
# 2️⃣ 財務資料
# ========================
def safe_margin(num, denom):
    if num is None or denom is None or denom <= 0:
        return None
    return round(num / denom * 100, 2)


def calc_diff(a, b):
    if a is None or b is None:
        return None
    return round(a - b, 2)


def fmt(v):
    return "-" if v is None else v


def build_output(result):
    cur = result["current"]
    prev = result["prev"]
    yoy = result["yoy"]
    qoq = result["qoq"]
    yoy_diff = result["yoy_diff"]

    return {
        "gross_margin": cur["gross"],
        "gross_margin_prev": prev["gross"],
        "gross_margin_yoy": yoy["gross"],
        "gross_margin_qoq": qoq["gross"],
        "gross_margin_yoy_diff": yoy_diff["gross"],
        "gross_margin_combined": f"{fmt(cur['gross'])} / {fmt(prev['gross'])} / {fmt(yoy['gross'])}",

        "operating_margin": cur["op"],
        "operating_margin_prev": prev["op"],
        "operating_margin_yoy": yoy["op"],
        "operating_margin_qoq": qoq["op"],
        "operating_margin_yoy_diff": yoy_diff["op"],
        "operating_margin_combined": f"{fmt(cur['op'])} / {fmt(prev['op'])} / {fmt(yoy['op'])}",

        "net_margin": cur["net"],
        "net_margin_prev": prev["net"],
        "net_margin_yoy": yoy["net"],
        "net_margin_qoq": qoq["net"],
        "net_margin_yoy_diff": yoy_diff["net"],
        "net_margin_combined": f"{fmt(cur['net'])} / {fmt(prev['net'])} / {fmt(yoy['net'])}",
    }


def get_profit_ratio(stock_id):
    try:
        df = api.taiwan_stock_financial_statement(
            stock_id=stock_id,
            start_date="2022-01-01",
        )

        if df.empty:
            return None

        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")

        pivot = df.pivot_table(
            index="date",
            columns="type",
            values="value",
            aggfunc="last",
        ).sort_index()

        cols = ["Revenue", "GrossProfit", "OperatingIncome", "IncomeAfterTaxes"]
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
                "gross": safe_margin(row["GrossProfit"], row["Revenue"]),
                "op": safe_margin(row["OperatingIncome"], row["Revenue"]),
                "net": safe_margin(row["IncomeAfterTaxes"], row["Revenue"]),
            }

        cur_m = calc(current)
        prev_m = calc(prev)
        yoy_m = calc(yoy)

        return {
            "current": cur_m,
            "prev": prev_m,
            "yoy": yoy_m,
            "qoq": {
                "gross": calc_diff(cur_m["gross"], prev_m["gross"]),
                "op": calc_diff(cur_m["op"], prev_m["op"]),
                "net": calc_diff(cur_m["net"], prev_m["net"]),
            },
            "yoy_diff": {
                "gross": calc_diff(cur_m["gross"], yoy_m["gross"]),
                "op": calc_diff(cur_m["op"], yoy_m["op"]),
                "net": calc_diff(cur_m["net"], yoy_m["net"]),
            },
        }

    except Exception as e:
        print(f"❌ profit error {stock_id}: {e}")
        return None


def extract_metric(res, key):
    if not res:
        return None, None, None
    return (
        res["current"].get(key),
        res["qoq"].get(key),
        res["yoy_diff"].get(key),
    )


# ========================
# 3️⃣ EPS
# ========================
def get_eps_analysis(stock_id, current_price):
    """
    回傳:
    (去年EPS, TTM_EPS, 預估今年EPS, 去年PER, TTM_PER, 預估PER)
    """
    try:
        params = {
            "dataset": "TaiwanStockFinancialStatements",
            "data_id": stock_id,
            "start_date": "2020-01-01",
            "token": API_TOKEN,
        }

        data = requests.get(api_url, params=params, timeout=10).json().get("data", [])
        if not data:
            return (None,) * 6

        df = pd.DataFrame(data)
        df = df[df["type"] == "EPS"]

        if df.empty:
            return (None,) * 6

        df["date"] = pd.to_datetime(df["date"])
        df["year"] = df["date"].dt.year
        df["season"] = df["date"].dt.quarter
        df["value"] = pd.to_numeric(df["value"], errors="coerce")

        df = df.sort_values("date").drop_duplicates(["year", "season"], keep="last")

        last_year = datetime.now().year - 1
        df_last = df[df["year"] == last_year]

        eps_last = None
        if df_last["season"].nunique() >= 4:
            eps_last = round(df_last["value"].sum(), 2)

        df_sorted = df.sort_values("date")
        df_ttm = df_sorted.tail(4)

        eps_ttm = None
        if len(df_ttm) == 4:
            eps_ttm = round(df_ttm["value"].sum(), 2)

        yearly_eps = df.groupby("year")["value"].sum().sort_index()

        eps_est = None
        if len(yearly_eps) >= 3:
            last_3 = yearly_eps.tail(3)
            start = last_3.iloc[0]
            end = last_3.iloc[-1]
            years = len(last_3) - 1

            if start > 0 and years > 0:
                cagr = (end / start) ** (1 / years) - 1
                eps_est = round(end * (1 + cagr), 2)

        def calc_per(price, eps):
            return round(price / eps, 2) if eps and eps > 0 else None

        per_last = calc_per(current_price, eps_last)
        per_ttm = calc_per(current_price, eps_ttm)
        per_est = calc_per(current_price, eps_est)

        return eps_last, eps_ttm, eps_est, per_last, per_ttm, per_est

    except Exception as e:
        print(f"❌ EPS error {stock_id}: {e}")
        return (None,) * 6


# ========================
# 4️⃣ 股利 / 殖利率
# ========================
def get_dividend_yield(stock_id, current_price=None):
    """
    回傳:
    {
        "dividend": 最近現金股利,
        "yield": 殖利率(%)
    }
    """
    try:
        params = {
            "dataset": "TaiwanStockDividend",
            "data_id": stock_id,
            "start_date": "2020-01-01",
            "token": API_TOKEN,
        }
        res = requests.get(api_url, params=params, timeout=10)

        if res.status_code != 200:
            return {"dividend": None, "yield": None}

        data = res.json().get("data", [])
        if not data:
            return {"dividend": None, "yield": None}

        df = pd.DataFrame(data)

        cash_cols = ["CashEarningsDistribution", "CashStatutorySurplus"]
        exist_cols = [c for c in cash_cols if c in df.columns]

        if not exist_cols:
            return {"dividend": None, "yield": None}

        df[exist_cols] = df[exist_cols].apply(pd.to_numeric, errors="coerce")
        df["year"] = pd.to_numeric(df["year"], errors="coerce")

        df_group = (
            df.groupby("year")[exist_cols]
            .sum()
            .sum(axis=1)
            .reset_index(name="cash_dividend")
            .sort_values("year", ascending=False)
        )

        dividend = None
        for val in df_group["cash_dividend"]:
            if val and val > 0:
                dividend = round(val, 2)
                break

        yield_pct = None

        try:
            params2 = {
                "dataset": "TaiwanStockPER",
                "data_id": stock_id,
                "start_date": "2023-01-01",
                "token": API_TOKEN,
            }
            res2 = requests.get(api_url, params=params2, timeout=10)
            data2 = res2.json().get("data", [])

            if data2:
                df2 = pd.DataFrame(data2)
                df2["date"] = pd.to_datetime(df2["date"])
                latest = df2.sort_values("date").iloc[-1]
                yield_pct = latest.get("dividend_yield")
                if yield_pct is not None:
                    yield_pct = round(float(yield_pct), 2)
        except Exception:
            pass

        if yield_pct is None and dividend and current_price and current_price > 0:
            yield_pct = round(dividend / current_price * 100, 2)

        return {
            "dividend": dividend,
            "yield": yield_pct,
        }

    except Exception as e:
        print(f"❌ 股利/殖利率錯誤 {stock_id}: {e}")
        return {"dividend": None, "yield": None}


# ========================
# 5️⃣ 技術指標
# ========================
def add_indicators(df):
    try:
        low_min = df["min"].rolling(9).min()
        high_max = df["max"].rolling(9).max()
        denom = (high_max - low_min).replace(0, pd.NA)

        # KD
        rsv = (df["close"] - low_min) / denom * 100
        df["K"] = rsv.ewm(com=2).mean()
        df["D"] = df["K"].ewm(com=2).mean()

        # 均線
        df["MA6"] = df["close"].rolling(6).mean()
        df["MA18"] = df["close"].rolling(18).mean()
        df["MA50"] = df["close"].rolling(50).mean()

        # 布林
        std = df["close"].rolling(18).std()
        df["BB_upper"] = df["MA18"] + 2 * std
        df["BB_lower"] = df["MA18"] - 2 * std

        # 乖離率
        df["BIAS6"] = (df["close"] - df["MA6"]) / df["MA6"] * 100
        df["BIAS18"] = (df["close"] - df["MA18"]) / df["MA18"] * 100
        df["BIAS50"] = (df["close"] - df["MA50"]) / df["MA50"] * 100

        # 近90天高低點
        df["BIAS6_90D_HIGH"] = df["BIAS6"].rolling(90).max()
        df["BIAS6_90D_LOW"] = df["BIAS6"].rolling(90).min()

        df["BIAS18_90D_HIGH"] = df["BIAS18"].rolling(90).max()
        df["BIAS18_90D_LOW"] = df["BIAS18"].rolling(90).min()

        df["BIAS50_90D_HIGH"] = df["BIAS50"].rolling(90).max()
        df["BIAS50_90D_LOW"] = df["BIAS50"].rolling(90).min()

        return df

    except Exception as e:
        print(f"❌ indicator error: {e}")
        return df


def get_MABias(df):
    """計算 MA6/18/50、最新乖離率、近90天乖離率 min/max"""
    if len(df) < 90:
        return {
            "ma6": None,
            "ma18": None,
            "ma50": None,
            "bias6": None,
            "bias18": None,
            "bias50": None,
            "bias6_min": None,
            "bias6_max": None,
            "bias18_min": None,
            "bias18_max": None,
            "bias50_min": None,
            "bias50_max": None,
        }

    periods = [6, 18, 50]
    stats = {}

    for p in periods:
        ma_series = df["close"].rolling(p).mean()
        ma_value = ma_series.iloc[-1]

        stats[f"ma{p}"] = round(ma_value, 2) if pd.notna(ma_value) else None

        if ma_value == 0 or pd.isna(ma_value):
            stats[f"bias{p}"] = None
            stats[f"bias{p}_min"] = None
            stats[f"bias{p}_max"] = None
            continue

        bias_series = (df["close"] - ma_series) / ma_series * 100
        latest_bias = bias_series.iloc[-1]
        bias_90 = bias_series.iloc[-90:]

        stats[f"bias{p}"] = round(latest_bias, 2) if pd.notna(latest_bias) else None
        stats[f"bias{p}_min"] = round(bias_90.min(), 2) if bias_90.notna().any() else None
        stats[f"bias{p}_max"] = round(bias_90.max(), 2) if bias_90.notna().any() else None

    return stats


# ========================
# 6️⃣ 評分
# ========================
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


# ========================
# 7️⃣ 單支股票分析
# ========================

def safe_pos(value, low, high):
    """計算 value 在 [low, high] 區間中的相對位置，回傳 0~1"""
    if value is None or low is None or high is None or high == low:
        return None
    return (value - low) / (high - low)


def get_tech_signal(
    close, chgPct, amp, volume_ok,
    k, d, prev_k, prev_d,
    bb_pct,
    bias6, bias18, bias50,
    bias6_min, bias6_max,
    bias18_min, bias18_max,
    bias50_min, bias50_max,
    ma18, prev_ma18, prev_close
):
    """
    回傳:
    {
        "signal_result": "買進訊號 / 賣出訊號 / 觀望訊號",
        "strategy": "買入 / 觀察 / 整理 / 出貨 / 減碼",
        "reason": "...",
        "signal_text": "條件摘要"
    }
    """
    reasons = []

    kd_gold_cross = prev_k <= prev_d and k > d
    kd_dead_cross = prev_k >= prev_d and k < d

    ma18_break = (
        ma18 is not None and prev_ma18 is not None
        and prev_close <= prev_ma18 and close > ma18
    )

    bias6_pos = safe_pos(bias6, bias6_min, bias6_max)
    bias18_pos = safe_pos(bias18, bias18_min, bias18_max)
    bias50_pos = safe_pos(bias50, bias50_min, bias50_max)

    # ===== 1) KD 分數 =====
    kd_score = 0
    if kd_gold_cross and k < 35:
        kd_score = 2
        reasons.append("KD低檔黃金交叉")
    elif kd_gold_cross:
        kd_score = 1
        reasons.append("KD黃金交叉")
    elif kd_dead_cross and k > 75:
        kd_score = -2
        reasons.append("KD高檔死亡交叉")
    elif kd_dead_cross:
        kd_score = -1
        reasons.append("KD死亡交叉")

    # ===== 2) 價量分數 =====
    vol_price_score = 0
    if chgPct > 0 and volume_ok:
        vol_price_score = 2
        reasons.append("價漲量增")
    elif chgPct > 0 and not volume_ok:
        vol_price_score = 1
        reasons.append("上漲但量能普通")
    elif chgPct < 0 and volume_ok:
        vol_price_score = -2
        reasons.append("價跌量增")
    elif chgPct < 0:
        vol_price_score = -1
        reasons.append("股價走弱")

    # ===== 3) 布林分數 =====
    bb_score = 0
    if bb_pct is not None:
        if bb_pct < 20:
            bb_score = 1
            reasons.append("接近布林下緣")
        elif bb_pct > 95:
            bb_score = -1
            reasons.append("接近布林上緣過熱")
        elif bb_pct > 80:
            bb_score = -0.5
            reasons.append("位於布林高檔區")

    # ===== 4) Bias 分數 =====
    bias_score = 0

    if bias6_pos is not None:
        if bias6_pos < 0.2:
            bias_score += 1
            reasons.append("Bias6接近90日低點")
        elif bias6_pos > 0.8:
            bias_score -= 1
            reasons.append("Bias6接近90日高點")

    if bias18_pos is not None:
        if bias18_pos < 0.2:
            bias_score += 1
            reasons.append("Bias18接近90日低點")
        elif bias18_pos > 0.8:
            bias_score -= 1
            reasons.append("Bias18接近90日高點")

    if bias50_pos is not None:
        if bias50_pos < 0.2:
            bias_score += 0.5
            reasons.append("Bias50偏低")
        elif bias50_pos > 0.8:
            bias_score -= 0.5
            reasons.append("Bias50偏高")

    # ===== 5) 趨勢分數 =====
    trend_score = 0
    if ma18 is not None and close > ma18:
        trend_score += 1
        reasons.append("股價站上月線")
    if bias18 is not None and bias18 > 0:
        trend_score += 0.5
    if bias50 is not None and bias50 > 0:
        trend_score += 0.5

    total_score = kd_score + vol_price_score + bb_score + bias_score + trend_score

    # ===== 訊號結果 =====
    if total_score >= 3:
        signal_result = "買進訊號"
    elif total_score <= -3:
        signal_result = "賣出訊號"
    else:
        signal_result = "觀望訊號"

    # ===== 策略 =====
    if signal_result == "買進訊號":
        if (bias6_pos is not None and bias6_pos > 0.9) or (bb_pct is not None and bb_pct > 95):
            strategy = "觀察"
            reason = "雖然技術面轉強，但短線過熱，不宜追價。"
        else:
            strategy = "買入"
            reason = "技術指標同步轉強，適合偏多操作。"

    elif signal_result == "賣出訊號":
        if kd_dead_cross and k > 75:
            strategy = "出貨"
            reason = "高檔轉弱且賣壓出現，應優先出貨。"
        else:
            strategy = "減碼"
            reason = "技術面轉弱，但中期趨勢未完全破壞，先減碼控風險。"

    else:
        if amp < 2 and not volume_ok:
            strategy = "整理"
            reason = "量縮且波動不大，屬整理格局。"
        else:
            strategy = "觀察"
            reason = "技術面方向不明，先觀察等待確認。"

    # ===== 若訊號與策略不同，額外補充原因 =====
    if signal_result == "買進訊號" and strategy != "買入":
        reason = f"雖然出現買進訊號，但因短線過熱或追價風險偏高，所以策略改為{strategy}。"

    if signal_result == "賣出訊號" and strategy != "出貨":
        reason = f"雖然出現賣出訊號，但中期趨勢未完全破壞，所以策略先採{strategy}。"

    return {
        "signal_result": signal_result,
        "strategy": strategy,
        "reason": reason,
        "signal_text": " / ".join(reasons) if reasons else "觀望"
    }


def process_stock(s):
    try:
        df = get_stock_data(s["stock_id"])
        if df.empty or len(df) < 90:
            return None

        df = add_indicators(df)
        latest, prev = df.iloc[-1], df.iloc[-2]

        chg = latest["close"] - prev["close"]
        chgPct = round((chg / prev["close"]) * 100, 2)
        chgamp = latest["max"] - latest["min"]
        amp = round((chgamp / prev["close"]) * 100, 2)

        # ===== EPS / 財務 / 殖利率 =====
        eps_res = get_eps_analysis(s["stock_id"], latest["close"])
        if not eps_res or not isinstance(eps_res, tuple):
            eps_res = (None,) * 6

        profit_res = get_profit_ratio(s["stock_id"]) or {
            "current": {},
            "qoq": {},
            "yoy_diff": {}
        }
        cur_g, qoq_g, yoy_g = extract_metric(profit_res, "gross")
        cur_o, qoq_o, yoy_o = extract_metric(profit_res, "op")
        cur_n, qoq_n, yoy_n = extract_metric(profit_res, "net")

        yield_pct = get_dividend_yield(s["stock_id"], latest["close"])
        ma_stats = get_MABias(df)

        # ===== 把 ma_stats 轉成 Python 原生型別 =====
        safe_ma_stats = {}
        for k2, v2 in ma_stats.items():
            if v2 is None or pd.isna(v2):
                safe_ma_stats[k2] = None
            else:
                safe_ma_stats[k2] = float(v2)

        # ===== 技術值 =====
        k = latest["K"] if pd.notna(latest["K"]) else 50
        d = latest["D"] if pd.notna(latest["D"]) else 50
        prev_k = prev["K"] if pd.notna(prev["K"]) else 50
        prev_d = prev["D"] if pd.notna(prev["D"]) else 50

        ma18 = latest["MA18"] if pd.notna(latest["MA18"]) else None
        prev_ma18 = prev["MA18"] if pd.notna(prev["MA18"]) else None

        close = latest["close"]
        prev_close = prev["close"]

        # ===== 成交量條件 =====
        volume = latest.get("volume", None)
        prev_volume = prev.get("volume", None)
        volume_ratio = None
        volume_add = None
        volume_ok = False

        if pd.notna(volume) and pd.notna(prev_volume) and prev_volume > 0:
            volume_ratio = round((volume / prev_volume - 1) * 100, 2)
            volume_add = round(volume - prev_volume, 0)
            volume_ok = bool(
                (volume >= prev_volume * 1.1) or ((volume - prev_volume) >= 500)
            )

        # ===== 布林位置 =====
        bb_upper = latest["BB_upper"] if "BB_upper" in latest else None
        bb_lower = latest["BB_lower"] if "BB_lower" in latest else None
        bb_pct = None
        if pd.notna(bb_upper) and pd.notna(bb_lower) and bb_upper != bb_lower:
            bb_pct = round((close - bb_lower) / (bb_upper - bb_lower) * 100, 1)

        # ===== Bias 值 =====
        bias6 = safe_ma_stats.get("bias6")
        bias18 = safe_ma_stats.get("bias18")
        bias50 = safe_ma_stats.get("bias50")

        bias6_min = safe_ma_stats.get("bias6_min")
        bias6_max = safe_ma_stats.get("bias6_max")
        bias18_min = safe_ma_stats.get("bias18_min")
        bias18_max = safe_ma_stats.get("bias18_max")
        bias50_min = safe_ma_stats.get("bias50_min")
        bias50_max = safe_ma_stats.get("bias50_max")

        # ===== 技術訊號判斷 =====
        signal_res = get_tech_signal(
            close=close,
            chgPct=chgPct,
            amp=amp,
            volume_ok=volume_ok,
            k=k,
            d=d,
            prev_k=prev_k,
            prev_d=prev_d,
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
            prev_close=prev_close
        )

        signal_result = signal_res["signal_result"]
        strategy = signal_res["strategy"]
        reason = signal_res["reason"]
        signal_text = signal_res["signal_text"]

        # ===== 對應舊版 sig =====
        if signal_result == "買進訊號":
            sig = 1
        elif signal_result == "賣出訊號":
            sig = -1
        else:
            sig = 0

        # ===== 額外操作標記 =====
        kd_buy = bool((prev_k <= prev_d) and (k > d))
        ma18_break = bool(
            ma18 is not None and prev_ma18 is not None and
            prev_close <= prev_ma18 and close > ma18
        )

        entry_note = ""
        if "短線過熱" in reason or "不宜追價" in reason:
            entry_note = "不追價"
        elif strategy == "買入" and kd_buy and ma18_break and k < 35:
            entry_note = "抄底"
        elif strategy == "買入" and ma18_break and chgPct >= 3:
            entry_note = "追漲"

        # ===== 評分 =====
        margin_score = calc_margin_score(cur_g, cur_o, cur_n)
        eps_score = calc_eps_score(eps_res[1], eps_res[2])
        trend_score = calc_trend_score(qoq_g, yoy_g, qoq_n, yoy_n)
        score = round(
            margin_score * 0.4 +
            eps_score * 0.3 +
            trend_score * 0.3,
            2
        )

        return {
            "name": s["name"],
            "code": s["stock_id"],
            "price": float(round(close, 2)),
            "chg": float(round(chg, 2)),
            "chgPct": float(chgPct),
            "amp": float(amp),

            "gross_margin": float(cur_g) if cur_g is not None else None,
            "gross_margin_qoq": float(qoq_g) if qoq_g is not None else None,
            "gross_margin_yoy_diff": float(yoy_g) if yoy_g is not None else None,

            "operating_margin": float(cur_o) if cur_o is not None else None,
            "operating_margin_qoq": float(qoq_o) if qoq_o is not None else None,
            "operating_margin_yoy_diff": float(yoy_o) if yoy_o is not None else None,

            "net_margin": float(cur_n) if cur_n is not None else None,
            "net_margin_qoq": float(qoq_n) if qoq_n is not None else None,
            "net_margin_yoy_diff": float(yoy_n) if yoy_n is not None else None,

            "eps_Y": float(eps_res[0]) if eps_res[0] is not None else None,
            "eps_ttm": float(eps_res[1]) if eps_res[1] is not None else None,
            "eps_est": float(eps_res[2]) if eps_res[2] is not None else None,

            "yield": yield_pct,

            "per_Y": float(eps_res[3]) if eps_res[3] is not None else None,
            "per_ttm": float(eps_res[4]) if eps_res[4] is not None else None,
            "per_est": float(eps_res[5]) if eps_res[5] is not None else None,

            "k": float(round(k, 1)),
            "d": float(round(d, 1)),
            "ma18": float(round(ma18, 2)) if ma18 is not None else None,
            "ma18_break": bool(ma18_break),
            "kd_buy": bool(kd_buy),
            "bb_pct": float(bb_pct) if bb_pct is not None else None,

            "volume": int(round(volume, 0)) if pd.notna(volume) else None,
            "prev_volume": int(round(prev_volume, 0)) if pd.notna(prev_volume) else None,
            "volume_ratio": float(volume_ratio) if volume_ratio is not None else None,
            "volume_add": int(round(volume_add, 0)) if volume_add is not None else None,
            "volume_ok": bool(volume_ok),

            **safe_ma_stats,

            "sig": int(sig),
            "signal_result": signal_result,
            "score": float(score),
            "strategy": strategy,
            "signal_text": signal_text,
            "reason": reason,
            "entry_note": entry_note
        }

    except Exception as e:
        print(f"❌ process error {s['stock_id']}: {e}")
        return None


# ========================
# 8️⃣ 全部股票
# ========================
def get_full_stock_analysis(stock_list):
    results = []
    for s in stock_list:
        data = process_stock(s)
        if data:
            results.append(data)
    return results