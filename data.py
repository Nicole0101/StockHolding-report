import logging
import requests
import pandas as pd
import os
from datetime import datetime, timedelta
from FinMind.data import DataLoader

API_TOKEN = os.getenv("FINMIND_TOKEN")
api_url = "https://api.finmindtrade.com/api/v4/data"
api = DataLoader()

# 停用所有來自 FinMind 的 Log 訊息
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
        required_cols = ["open", "close", "max", "min"]
        print(df.head())
        df = df[required_cols].dropna()
        return df
    except Exception as e:
        print(f"❌ get_stock_data error {stock_id}: {e}")
        return pd.DataFrame()


# ========================
# 2️⃣ 財務資料
# ========================
def get_profit_ratio(stock_id):
    try:
        df = api.taiwan_stock_financial_statement(
            stock_id=stock_id, start_date="2023-01-01"
        )
        if df.empty:
            return None, None, None
        df = df.sort_values("date")
        latest = df.groupby("type").last()["value"]
        revenue = latest.get("Revenue", 0)
        GrossProfit = latest.get("GrossProfit", 0)
        OperatingIncome = latest.get("OperatingIncome")
        IncomeAfterTaxes = latest.get("IncomeAfterTaxes", 0)
        print("stock_id:", stock_id, "Revenue", revenue,
              GrossProfit, OperatingIncome, IncomeAfterTaxes)
        if revenue == 0:
            return None, None, None
        return (
            round(GrossProfit / revenue * 100, 2),
            round(OperatingIncome / revenue * 100, 2),
            round(IncomeAfterTaxes / revenue * 100, 2),
        )
    except Exception as e:
        print(f"❌ profit error {stock_id}: {e}")
        return None, None, None


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
        # 1. 取得財報資料 (拉長到 3 年確保 TTM 計算完整)
        start_date = (datetime.now() - timedelta(days=365*3)
                      ).strftime("%Y-%m-%d")

        params = {
            "dataset": "TaiwanStockFinancialStatements",
            "data_id": str(stock_id),
            "start_date": start_date,
            "token": API_TOKEN
        }
        res = requests.get(api_url, params=params)
        data = res.json().get("data", [])

        if not data:
            print(f"⚠️ {stock_id} 無財報資料")
            return None, None, None, None, None, None

        df = pd.DataFrame(data)
        # 過濾 EPS 資料 (FinMind 中通常標註為 'EPS')
        df = df[df["type"] == "EPS"].copy()
        df["date"] = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.sort_values("date")

        # --- 重要：將累計 EPS 轉換為單季 EPS ---
        # 台灣財報 Q1=Q1, Q2=Q1+Q2, Q3=Q1+Q2+Q3, Q4=全年
        df["year"] = df["date"].dt.year
        df["quarter"] = df["date"].dt.quarter

        # 計算單季值：如果是同一年，後一季減去前一季
        df["single_eps"] = df.groupby(
            "year")["value"].diff().fillna(df["value"])

        # --- A. 去年全年 EPS ---
        last_year = datetime.now().year - 1
        # 直接抓去年 Q4 的累計值，那就是全年 EPS
        df_last_q4 = df[(df["year"] == last_year) & (df["quarter"] == 4)]
        if not df_last_q4.empty:
            last_Y_eps = round(df_last_q4["value"].iloc[-1], 2)
        else:
            # 如果還沒出 Q4，就用現有的加總 (非累計法)
            last_Y_eps = round(df[df["year"] == last_year]
                               ["single_eps"].sum(), 2)

        # --- B. 近四季 TTM EPS ---
        # 取最後四筆單季 EPS 加總
        if len(df) >= 4:
            ttm_eps = round(df["single_eps"].tail(4).sum(), 2)

        # --- C. 推估今年 EPS (使用營收 YoY 修正) ---
        try:
            rev_params = {
                "dataset": "TaiwanStockMonthRevenue",
                "data_id": str(stock_id),
                "start_date": (datetime.now() - timedelta(days=365*2)).strftime("%Y-%m-%d"),
                "token": API_TOKEN
            }
            rev_res = requests.get(api_url, params=rev_params)
            rev_data = rev_res.json().get("data", [])

            if rev_data and ttm_eps:
                rev_df = pd.DataFrame(rev_data)
                rev_df["revenue"] = pd.to_numeric(
                    rev_df["revenue"], errors="coerce")
                # 計算近三個月平均營收年增率
                # 假設資料已有 'revenue' 且按日期排序
                rev_df = rev_df.sort_values("date")
                # FinMind 營收資料通常有現成的 YoY，若無則手動計算
                rev_df["YoY"] = rev_df["revenue"].pct_change(12)
                growth = rev_df["YoY"].tail(3).mean()

                if pd.notna(growth):
                    est_eps = round(ttm_eps * (1 + growth), 2)
                else:
                    est_eps = ttm_eps
        except Exception as e:
            print(f"⚠️ 營收計算失敗: {e}")
            est_eps = ttm_eps

        # 2. 計算 PER
        def calc_per(p, e):
            return round(p / e, 2) if e and e > 0 else None
        per_last = calc_per(current_price, last_Y_eps)
        per_ttm = calc_per(current_price, ttm_eps)
        per_est = calc_per(current_price, est_eps)
        return last_Y_eps, ttm_eps, est_eps, per_last, per_ttm, per_est

    except Exception as e:
        print(f"❌ 錯誤: {e}")
        return None, None, None, None, None, None


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
        denom = (high_max - low_min)
        denom = denom.replace(0, pd.NA)
        rsv = (df["close"] - low_min) / denom * 100
        df["K"] = rsv.ewm(com=2).mean()
        df["D"] = df["K"].ewm(com=2).mean()
        ma20 = df["close"].rolling(20).mean()
        std = df["close"].rolling(20).std()
        df["BB_upper"] = ma20 + 2 * std
        df["BB_lower"] = ma20 - 2 * std
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

# ========================
# 5️⃣ 單支股票分析
# ========================


def process_stock(s):
    try:
        # 1. 基礎資料獲取與技術指標計算
        df = get_stock_data(s["stock_id"])
        if df.empty or len(df) < 60:
            return None
        df = add_indicators(df)
        latest, prev = df.iloc[-1], df.iloc[-2]

        # 2. 計算漲跌幅與震幅
        chg = latest["close"] - latest["open"]
        chgPct = round((chg / prev["close"]) * 100, 2)
        amp = round(
            ((latest["max"] - latest["min"]) / prev["close"]) * 100, 2)

        # 3. 呼叫各項分析函式 (結構化資料)
        # EPS 分析回傳: (last_year_eps, ttm_eps, est_eps, per_last, per_ttm, per_est)
        #   eps_res = get_eps_analysis(s["stock_id"], latest["close"])
        eps_res = get_eps_analysis(s["stock_id"], latest["close"]) or (None,)*6
        print("stock_id ", stock_id, "eps_res: ", eps_res)
        # 獲取毛利與淨利率
        #   gm, om, nm = get_profit_ratio(s["stock_id"]) or (None, None, None)
        # 毛利率（避免 0 被吃掉）
        profit_res = get_profit_ratio(s["stock_id"])
        if profit_res is None:
            gm, om, nm = None, None, None
        else:
            gm, om, nm = profit_res
        print("stock_id ", "profit_res: ", profit_res)
        # 獲取殖利率
        yield_pct = get_dividend_yield(s["stock_id"], latest["close"])

        # 獲取均線與乖離率
        ma_stats = get_MABias(df)

        # 4. 策略邏輯判斷
        k = latest["K"] if pd.notna(latest["K"]) else 50
        strategy = (
            "反彈🔥" if amp > 5 and k < 30 else
            "出貨⚠" if amp > 5 and k > 70 else
            "整理" if amp < 2 else
            "觀察"
        )

        # 5. 回傳結構化字典
        return {
            "name": s["name"][:3],
            "code": s["stock_id"],
            "price": round(latest["close"], 2),
            "chg": round(chg, 2),
            "chgPct": chgPct,
            "amp": amp,
            "gross_margin": gm,
            "operating_Margin": om,
            "net_margin": nm,
            # EPS 與 PER 相關資料 (從元組中取值)
            "eps_Y": eps_res[0] if eps_res[0] is not None else "-",
            "eps_ttm": eps_res[1] if eps_res[1] is not None else "-",
            "eps_est": eps_res[2] if eps_res[2] is not None else "-",
            "eps_estcombined": f"{eps_res[1] if eps_res[1] is not None else '-'} / {eps_res[2] if eps_res[2] is not None else '-'}",
            "yield": yield_pct if yield_pct is not None else "-",
            "per_Y": eps_res[3] if eps_res[3] is not None else "-",
            "per_ttm": eps_res[4] if eps_res[4] is not None else "-",
            "per_est": eps_res[5] if eps_res[5] is not None else "-",
            "per_estcombined": f"{eps_res[3] if eps_res[3] is not None else '-'} / {eps_res[4] if eps_res[4] is not None else '-'}/ {eps_res[5] if eps_res[5] is not None else '-'}",
            "k": round(k, 1),
            "bb": (
                "上軌" if latest["close"] > latest["BB_upper"] else
                "下軌" if latest["close"] < latest["BB_lower"] else
                "中軌"
            ),
            # 自動展開 ma6, bias6, ma18, bias18, ma50, bias50 等欄位
            **ma_stats,
            "strategy": strategy
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
