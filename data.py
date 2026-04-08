import logging
import requests
import pandas as pd
import os
from loguru import logger
from datetime import datetime, timedelta
from FinMind.data import DataLoader

API_TOKEN = os.getenv("FINMIND_TOKEN")
api_url = "https://api.finmindtrade.com/api/v4/data"
api = DataLoader()

# 停用所有來自 FinMind 的 Log 訊息
logger.remove()
logging.getLogger('FinMind').setLevel(logging.WARNING)


# ========================
# 1️⃣ 價格資料
# ========================
def get_stock_data(stock_id):
    try:
        params = {
            "dataset": "TaiwanStockPrice",
            "data_id": str(stock_id),
            "start_date": "2023-01-01",
            "token": API_TOKEN
        }
        res = requests.get(api_url, params=params, timeout=10)
        data = res.json()

        if "data" not in data or len(data["data"]) == 0:
            return pd.DataFrame()

        df = pd.DataFrame(data["data"])

        # FinMind 股價資料常見成交量欄位
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
            # 股數轉成張
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
    #   num = to_number(num)
    #   denom = to_number(denom)
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

    output = {
        # ===== 毛利率 =====
        "gross_margin": cur["gross"],
        "gross_margin_prev": prev["gross"],
        "gross_margin_yoy": yoy["gross"],
        "gross_margin_qoq": qoq["gross"],
        "gross_margin_yoy_diff": yoy_diff["gross"],
        "gross_margin_combined": f"{fmt(cur['gross'])} / {fmt(prev['gross'])} / {fmt(yoy['gross'])}",

        # ===== 營益率 =====
        "operating_margin": cur["op"],
        "operating_margin_prev": prev["op"],
        "operating_margin_yoy": yoy["op"],
        "operating_margin_qoq": qoq["op"],
        "operating_margin_yoy_diff": yoy_diff["op"],
        "operating_margin_combined": f"{fmt(cur['op'])} / {fmt(prev['op'])} / {fmt(yoy['op'])}",

        # ===== 淨利率 =====
        "net_margin": cur["net"],
        "net_margin_prev": prev["net"],
        "net_margin_yoy": yoy["net"],
        "net_margin_qoq": qoq["net"],
        "net_margin_yoy_diff": yoy_diff["net"],
        "net_margin_combined": f"{fmt(cur['net'])} / {fmt(prev['net'])} / {fmt(yoy['net'])}",
    }

    return output


def get_profit_ratio(stock_id):
    try:
        df = api.taiwan_stock_financial_statement(
            stock_id=stock_id,
            start_date="2022-01-01"  # 至少抓2年以上
        )

        if df.empty:
            return None

        # ===== 基本整理 =====
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")

        # ===== pivot 成每季一列 =====
        pivot = df.pivot_table(
            index="date",
            columns="type",
            values="value",
            aggfunc="last"
        ).sort_index()

        # ===== 只留必要欄位 =====
        cols = ["Revenue", "GrossProfit",
                "OperatingIncome", "IncomeAfterTaxes"]
        pivot = pivot[cols].dropna()

        if len(pivot) < 5:
            return None

        # ===== 抓三個時間點 =====
        current = pivot.iloc[-1]       # 本期
        prev = pivot.iloc[-2]          # 上季
        yoy = pivot.iloc[-5]           # 去年同期（4季前）

        # ===== 計算三率 =====
        def calc(row):
            return {
                "gross": safe_margin(row["GrossProfit"], row["Revenue"]),
                "op": safe_margin(row["OperatingIncome"], row["Revenue"]),
                "net": safe_margin(row["IncomeAfterTaxes"], row["Revenue"]),
            }

        cur_m = calc(current)
        prev_m = calc(prev)
        yoy_m = calc(yoy)

        # ===== QoQ / YoY =====
        result = {
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
            }
        }

        return result
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
    回傳: (去年EPS, TTM_EPS, 預估今年EPS, 去年PER, TTM_PER, 預估PER)
    """
    # 初始化回傳值
    last_Y_eps, ttm_eps, est_eps = None, None, None
    per_last, per_ttm, per_est = None, None, None

    try:
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {
            "dataset": "TaiwanStockFinancialStatements",
            "data_id": stock_id,
            "start_date": "2020-01-01",  # ⬅️ 至少抓3年以上
            "token": API_TOKEN
        }

        data = requests.get(url, params=params).json().get("data", [])
        if not data:
            return None

        df = pd.DataFrame(data)
        df = df[df["type"] == "EPS"]

        if df.empty:
            return None

        # ===== 基本整理 =====
        df["date"] = pd.to_datetime(df["date"])
        df["year"] = df["date"].dt.year
        df["season"] = df["date"].dt.quarter
        df["value"] = pd.to_numeric(df["value"], errors="coerce")

        # 去重（同一季只留最新）
        df = df.sort_values("date").drop_duplicates(
            ["year", "season"], keep="last"
        )

        # ===== eps_last：去年全年 =====
        last_year = datetime.now().year - 1
        df_last = df[df["year"] == last_year]

        eps_last = None
        if df_last["season"].nunique() >= 4:
            eps_last = round(df_last["value"].sum(), 2)

        # ===== eps_ttm：最近四季 =====
        df_sorted = df.sort_values("date")
        df_ttm = df_sorted.tail(4)

        eps_ttm = None
        if len(df_ttm) == 4:
            eps_ttm = round(df_ttm["value"].sum(), 2)

        # ===== eps_est：三年成長預估 =====
        yearly_eps = (
            df.groupby("year")["value"]
            .sum()
            .sort_index()
        )

        eps_est = None
        if len(yearly_eps) >= 3:
            last_3 = yearly_eps.tail(3)

            start = last_3.iloc[0]
            end = last_3.iloc[-1]
            years = len(last_3) - 1

            if start > 0 and years > 0:
                cagr = (end / start) ** (1 / years) - 1
                eps_est = round(end * (1 + cagr), 2)

         # ===== PER =====
        def calc_per(price, eps):
            return round(price / eps, 2) if eps and eps > 0 else None

        per_last = calc_per(current_price, eps_last)
        per_ttm = calc_per(current_price, eps_ttm)
        per_est = calc_per(current_price, eps_est)

        return eps_last, eps_ttm, eps_est, per_last, per_ttm, per_est

    except Exception as e:
        print(f"❌ 錯誤: {e}")
        return (None,) * 6


# ===============================================
def get_dividend_yield(stock_id, current_price=None):
    """
    回傳:
    {
        "dividend": 最近現金股利,
        "yield": 殖利率(%)
    }
    """
    try:
        # =====================
        # 1️⃣ 抓股利
        # =====================
        params = {
            "dataset": "TaiwanStockDividend",
            "data_id": stock_id,
            "start_date": "2020-01-01",
            "token": API_TOKEN
        }
        res = requests.get(api_url, params=params, timeout=10)

        if res.status_code != 200:
            return {"dividend": None, "yield": None}

        data = res.json().get("data", [])
        if not data:
            return {"dividend": None, "yield": None}

        df = pd.DataFrame(data)

        # ===== 找現金股利欄位 =====
        cash_cols = [
            "CashEarningsDistribution",
            "CashStatutorySurplus"
        ]
        exist_cols = [c for c in cash_cols if c in df.columns]

        if not exist_cols:
            return {"dividend": None, "yield": None}

        # ===== 數值處理 =====
        df[exist_cols] = df[exist_cols].apply(
            pd.to_numeric, errors="coerce"
        )
        df["year"] = pd.to_numeric(df["year"], errors="coerce")

        # ===== 同年加總 =====
        df_group = (
            df.groupby("year")[exist_cols]
            .sum()
            .sum(axis=1)
            .reset_index(name="cash_dividend")
            .sort_values("year", ascending=False)
        )

        # ===== 找最近有配息 =====
        dividend = None
        for val in df_group["cash_dividend"]:
            if val and val > 0:
                dividend = round(val, 2)
                break

        # =====================
        # 2️⃣ 殖利率
        # =====================
        yield_pct = None

        # 👉 優先用 API（比較準）
        try:
            params2 = {
                "dataset": "TaiwanStockPER",
                "data_id": stock_id,
                "start_date": "2023-01-01",
                "token": API_TOKEN
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

        except:
            pass

        # 👉 fallback（自己算）
        if yield_pct is None and dividend and current_price:
            if current_price > 0:
                yield_pct = round(dividend / current_price * 100, 2)

        return {
            "dividend": dividend,
            "yield": yield_pct
        }

    except Exception as e:
        print(f"❌ 股利/殖利率錯誤 {stock_id}: {e}")
        return {"dividend": None, "yield": None}
    try:
        params = {
            "dataset": "TaiwanStockPER",
            "data_id": stock_id,
            "start_date": "2023-01-01",
            "token": API_TOKEN
        }
        res = requests.get(api_url, params=params)
        data = res.json().get("data", [])
        if not data:
            return None
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
        latest = df.iloc[-1]
        yield_pct = latest.get("dividend_yield")
        if yield_pct is None:
            return None
        return round(float(yield_pct), 2)
    except Exception as e:
        print(f"殖利率錯誤: {stock_id}", e)
        return None


# ========================
# 4️⃣ 技術指標
# ========================
def add_indicators(df):
    try:
        low_min = df["min"].rolling(9).min()
        high_max = df["max"].rolling(9).max()
        denom = (high_max - low_min).replace(0, pd.NA)

        rsv = (df["close"] - low_min) / denom * 100
        df["K"] = rsv.ewm(com=2).mean()
        df["D"] = df["K"].ewm(com=2).mean()

        # 月線 / 均線
        df["MA5"] = df["close"].rolling(5).mean()
        df["MA10"] = df["close"].rolling(10).mean()
        df["MA20"] = df["close"].rolling(20).mean()   # 月線
        df["MA60"] = df["close"].rolling(60).mean()

        # 布林
        std = df["close"].rolling(20).std()
        df["BB_upper"] = df["MA20"] + 2 * std
        df["BB_lower"] = df["MA20"] - 2 * std

        return df
    except Exception as e:
        print(f"❌ indicator error: {e}")
        return df


# 均線及乖離率=========================
def get_MABias(df):
    """  計算均線值與對應的乖離率    傳入: 包含 close 欄位的 DataFrame    回傳: 包含 ma 與 bias 的字典 """
    # 確保資料量足夠計算最大窗格 (50)
    if len(df) < 50:
        return {
            "ma6": None, "ma18": None, "ma50": None,
            "bias6": None, "bias18": None, "bias50": None
        }

    latest_close = df["close"].iloc[-1]

    # 定義要計算的週期
    periods = [6, 18, 50]
    stats = {}

    for p in periods:
        # 計算均線 (取最後一筆)
        ma_value = df["close"].rolling(p).mean().iloc[-1]
        stats[f"ma{p}"] = round(ma_value, 2)

        # 計算乖離率
        if ma_value == 0 or pd.isna(ma_value):
            stats[f"bias{p}"] = None
        else:
            bias = (latest_close - ma_value) / ma_value * 100
            stats[f"bias{p}"] = round(bias, 2)

    return stats


#   margin_score（毛利品質）
def calc_margin_score(gross, op, net):
    score = 0
    if gross is not None:
        score += gross * 0.4
    if op is not None:
        score += op * 0.3
    if net is not None:
        score += net * 0.3
    return round(score, 2)


#   eps_score（成長性）
def calc_eps_score(eps_ttm, eps_est):
    if eps_ttm is None or eps_est is None or eps_ttm <= 0:
        return 0
    growth = (eps_est - eps_ttm) / eps_ttm * 100
    return round(growth, 2)


#   trend_score（動能）
def calc_trend_score(qoq_g, yoy_g, qoq_n, yoy_n):
    vals = [qoq_g, yoy_g, qoq_n, yoy_n]
    vals = [v for v in vals if v is not None]
    if not vals:
        return 0
    return round(sum(vals) / len(vals), 2)

# ========================
# 5️⃣ 單支股票分析
# ========================


def process_stock(s):
    try:
        df = get_stock_data(s["stock_id"])
        if df.empty or len(df) < 60:
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

        # ===== 技術值 =====
        k = latest["K"] if pd.notna(latest["K"]) else 50
        d = latest["D"] if pd.notna(latest["D"]) else 50
        prev_k = prev["K"] if pd.notna(prev["K"]) else 50
        prev_d = prev["D"] if pd.notna(prev["D"]) else 50

        ma20 = latest["MA20"] if pd.notna(latest["MA20"]) else None
        prev_ma20 = prev["MA20"] if pd.notna(prev["MA20"]) else None

        close = latest["close"]
        prev_close = prev["close"]

        # ===== KD 買點 =====
        kd_buy = (prev_k <= prev_d) and (k > d)
        kd_low_buy = kd_buy and k < 35

        # ===== 月線買點 =====
        ma20_break = (
            ma20 is not None and prev_ma20 is not None and
            prev_close <= prev_ma20 and close > ma20
        )

        # ===== 成交量條件 =====
        volume = latest.get("volume", None)
        prev_volume = prev.get("volume", None)
        volume_ratio = None
        volume_add = None
        volume_ok = False

        if pd.notna(volume) and pd.notna(prev_volume) and prev_volume > 0:
            volume_ratio = round((volume / prev_volume - 1) * 100, 2)
            volume_add = round(volume - prev_volume, 0)
            volume_ok = (volume >= prev_volume * 1.1) or ((volume - prev_volume) >= 500)

        # ===== 布林位置 =====
        bb_upper = latest["BB_upper"]
        bb_lower = latest["BB_lower"]
        bb_pct = None
        if pd.notna(bb_upper) and pd.notna(bb_lower) and bb_upper != bb_lower:
            bb_pct = round((close - bb_lower) / (bb_upper - bb_lower) * 100, 1)

        # ===== 訊號判斷 =====
        signal_tags = []

        if kd_buy:
            signal_tags.append("KD買點")

        if ma20_break:
            signal_tags.append("站上月線")

        if volume_ok:
            signal_tags.append("量增")
        else:
            signal_tags.append("量不足")

        entry_note = ""
        if kd_low_buy and ma20_break:
            entry_note = "抄底"
        elif ma20_break and chgPct >= 3:
            entry_note = "追漲"

        if entry_note:
            signal_tags.append(entry_note)

        # 最終訊號
        if kd_buy and ma20_break and volume_ok:
            sig = 1
            strategy = "買入"
        elif k > 75 and d > 70 and chgPct < 0:
            sig = -1
            strategy = "出貨⚠"
        elif amp < 2:
            sig = 0
            strategy = "整理"
        else:
            sig = 0
            strategy = "觀察"

        signal_text = " / ".join(signal_tags) if signal_tags else "觀望"

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
            "name": s["name"][:3],
            "code": s["stock_id"],
            "price": round(close, 2),
            "chg": round(chg, 2),
            "chgPct": chgPct,
            "amp": amp,

            "gross_margin": cur_g,
            "gross_margin_qoq": qoq_g,
            "gross_margin_yoy_diff": yoy_g,

            "operating_margin": cur_o,
            "operating_margin_qoq": qoq_o,
            "operating_margin_yoy_diff": yoy_o,

            "net_margin": cur_n,
            "net_margin_qoq": qoq_n,
            "net_margin_yoy_diff": yoy_n,

            "eps_Y": eps_res[0] if eps_res[0] is not None else "-",
            "eps_ttm": eps_res[1] if eps_res[1] is not None else "-",
            "eps_est": eps_res[2] if eps_res[2] is not None else "-",
            "yield": yield_pct,
            "per_Y": eps_res[3] if eps_res[3] is not None else "-",
            "per_ttm": eps_res[4] if eps_res[4] is not None else "-",
            "per_est": eps_res[5] if eps_res[5] is not None else "-",

            "k": round(k, 1),
            "d": round(d, 1),
            "ma20": round(ma20, 2) if ma20 is not None else "-",
            "ma20_break": ma20_break,
            "kd_buy": kd_buy,
            "bb_pct": bb_pct,

            "volume": round(volume, 0) if pd.notna(volume) else "-",
            "prev_volume": round(prev_volume, 0) if pd.notna(prev_volume) else "-",
            "volume_ratio": volume_ratio,
            "volume_add": volume_add,
            "volume_ok": volume_ok,

            **ma_stats,
            "sig": sig,
            "score": score,
            "strategy": strategy,
            "signal_text": signal_text,
            "entry_note": entry_note
        }

    except Exception as e:
        print(f"❌ process error {s['stock_id']}: {e}")
        return None


# ========================
# 6️⃣ 全部股票
# ========================


def get_full_stock_analysis(stock_list):
    results = []
    for s in stock_list:
        data = process_stock(s)
        if data:
            results.append(data)
    return results
