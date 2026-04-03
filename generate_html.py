import pandas as pd
import requests
from jinja2 import Template
from datetime import datetime, timedelta
import os

FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")

# =========================
# 抓股價
# =========================
def get_stock_data(stock_id):
    try:
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {
            "dataset": "TaiwanStockPrice",
            "data_id": stock_id,
            "start_date": "2022-01-01",
            "token": FINMIND_TOKEN
        }

        res = requests.get(url, params=params)
        data = res.json().get("data", [])

        df = pd.DataFrame(data)
        if df.empty:
            return None
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")

        return df

    except Exception as e:
        print("抓資料錯誤:", stock_id, e)
        return None

# ===============================================
def get_dividend(stock_id):
    try:
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {
            "dataset": "TaiwanStockDividend",
            "data_id": stock_id,
            "start_date": "2022-01-01",
            "token": FINMIND_TOKEN
        }

        res = requests.get(url, params=params)
        if res.status_code != 200:
            print(f"{stock_id} API失敗:", res.status_code)
            return None

        data = res.json().get("data", [])
        if not data:
            return None

        df = pd.DataFrame(data)

        # 日期
        df["date"] = pd.to_datetime(df.get("date"), errors="coerce")
        df = df.dropna(subset=["date"])

        # 欄位判斷
        if "CashEarningsDistribution" in df.columns:
            col = "CashEarningsDistribution"
        elif "CashDividendPayment" in df.columns:
            col = "CashDividendPayment"
        else:
            return None

        df["cash_dividend"] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["cash_dividend"])

        if df.empty:
            return None

        # 年份
        df["year"] = df["date"].dt.year

        current_year = datetime.now().year
        last_year = current_year - 1

        # 👉 優先抓去年
        df_last = df[df["year"] == last_year]

        # 👉 如果去年沒有 → 抓最新一年
        if df_last.empty:
            latest_year = df["year"].max()
            df_last = df[df["year"] == latest_year]

        if df_last.empty:
            return None

        total_div = df_last["cash_dividend"].sum()
        count = df_last["cash_dividend"].count()

        if count == 0:
            return None

        # 👉 判斷完整 vs 累計
        if count >= 4:
            return round(total_div, 2)
        else:
            return f"{round(total_div,2)}（累計{count}季）"

    except Exception as e:
        print(f"股利錯誤: {stock_id}", e)
        return None

# ===============================================
def get_eps(stock_id):
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockFinancialStatements",
        "data_id": stock_id,
        "start_date": "2022-01-01",
        "token": FINMIND_TOKEN
    }
    res = requests.get(url, params=params)
    data = res.json().get("data", [])
    df = pd.DataFrame(data)
    if df.empty:
        return None
    # ✅ 正確縮排（和 if 同層）
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["type"] == "EPS"]
    return df.sort_values("date")

# ================================================
def est_eps(stock_id):
    api = DataLoader()
    eps_df = api.taiwan_stock_eps(stock_id=stock_id)
    eps_df = eps_df.sort_values("date", ascending=False).head(4)
    ttm_eps = eps_df["eps"].sum()

    rev = api.taiwan_stock_month_revenue(stock_id=stock_id)
    rev["YoY"] = rev["revenue"].pct_change(12)
    growth = rev.sort_values("date").tail(3)["YoY"].mean()
    estimated_eps = ttm_eps * (1 + growth)
    return round(ttm_eps, 2), round(estimated_eps, 2)

# =========================
# 指標
# =========================
def add_indicators(df):
    # KD
    low_min = df["min"].rolling(9).min()
    high_max = df["max"].rolling(9).max()
    rsv = (df["close"] - low_min) / (high_max - low_min) * 100
    df["K"] = rsv.ewm(com=2).mean()
    df["D"] = df["K"].ewm(com=2).mean()

    # 布林
    ma20 = df["close"].rolling(20).mean()
    std = df["close"].rolling(20).std()
    df["BB_upper"] = ma20 + 2 * std
    df["BB_lower"] = ma20 - 2 * std

    return df

# =========================
# 距離（你指定版本）
# =========================
def calc_dist(price, ma):
    if ma == 0 or pd.isna(ma):
        return None
    return round((price - ma) / ma * 100, 2)

# =========================
# 單股處理🔥
# =========================
def process_stock(s):
    try:
        df = get_stock_data(str(s["stock_id"]))
        if df is None or len(df) < 60:
            return None

        df = add_indicators(df)

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # ===== 漲跌 =====
        chg = latest["close"] - prev["close"]
        chgPct = (chg / prev["close"]) * 100

        # ===== 震幅 =====
        amp = ((latest["max"] - latest["min"]) / prev["close"]) * 100

        # ===== EPS =====
        eps_df = get_eps(s["stock_id"])
        last_eps = None
        eps_note = ""
        quarters = 0

        if eps_df is not None and not eps_df.empty:
            latest_year = eps_df["date"].dt.year.max()
            year_df = eps_df[eps_df["date"].dt.year == latest_year]

            eps_sum = year_df["value"].sum()
            quarters = len(year_df)

            last_eps = round(eps_sum, 2)

            if quarters < 4:
                eps_note = f"({quarters})"

        # ===== 殖利率 =====
        yield_pct = None
        dividend = get_dividend(s["stock_id"])
        # 👉 沒資料
        if dividend is None:
            yield_pct = None
        else:
        # 👉 如果是 "3.5（累計2季）" 這種字串 → 取數字
        if isinstance(dividend, str):
            try:
                dividend_value = float(dividend.split("（")[0])
            except:
                dividend_value = None
        else:
            dividend_value = dividend
        # 👉 計算殖利率
        if dividend_value and latest["close"] > 0:
            yield_pct = round(dividend_value / latest["close"] * 100, 2)

        # ===== PER =====
        per = None
        if last_eps not in [None, 0]:
            per = round(latest["close"] / last_eps, 2)

        # ===== 預估 EPS =====
        est_eps = None
        if last_eps:
            growth = 0.1
            est_eps = round(last_eps * (1 + growth), 2)

        # ===== 均線 =====
        ma20 = df["close"].rolling(20).mean().iloc[-1]
        ma60 = df["close"].rolling(60).mean().iloc[-1]

        dist20 = calc_dist(latest["close"], ma20)
        dist60 = calc_dist(latest["close"], ma60)

        k = latest["K"]
        d = latest["D"]

        # ===== 策略 =====
        if amp > 5 and k < 30:
            strategy = "反彈🔥"
        elif amp > 5 and k > 70:
            strategy = "出貨⚠"
        elif amp < 2:
            strategy = "整理"
        else:
            strategy = "觀察"

        return {
            "name": s["name"],
            "code": s["stock_id"],
            "price": round(latest["close"], 2),
            "chg": round(chg, 2),
            "chgPct": round(chgPct, 2),
            "amp": round(amp, 2),
            "eps_last": f"{last_eps}{eps_note}" if last_eps else "-",
            "yield": yield_pct,
            "per": per if per else "-",
            "est_eps": est_eps if est_eps else "-",

            "dist20": dist20,
            "dist60": dist60,
            "k": round(k, 1),
            "d": round(d, 1),

            "bb": "上軌" if latest["close"] > latest["BB_upper"]
                  else "下軌" if latest["close"] < latest["BB_lower"]
                  else "中軌",

            "sig": "buy" if k < 30 else "sell" if k > 70 else "hold",
            "strategy": strategy
        }

    except Exception as e:
        print("單股錯誤:", s["stock_id"], e)
        return None
    print(s["stock_id"], last_eps, yield_pct, per, est_eps)

# =========================
# 主程式🔥
# =========================
def main():

    import json

    # 讀股票清單
    df = pd.read_csv("stocks.csv", sep="\t", encoding="utf-8-sig")
    df = df.rename(columns={"Ticker": "stock_id", "Name": "name"})
    stock_list = df.to_dict(orient="records")

    results = []

    # ✅ 一定要在 main 裡面
    results = []
    for s in stock_list:
        data = process_stock(s)
        if data:
            results.append(data)

    # ✅ 放在迴圈外
    if not results:
        print("⚠️ 無資料")
        return

    print("結果數量:", len(results))

    # 存 JSON
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 排序🔥
    sorted_stocks = sorted(results, key=lambda x: x["chgPct"], reverse=True)

    top_names = ", ".join([s["name"] for s in sorted_stocks[:5]])
    weak_names = ", ".join([s["name"] for s in sorted_stocks[-5:]])

    rebound_list = [s["name"] for s in results if "反彈" in s.get("strategy", "")]
    selloff_list = [s["name"] for s in results if "出貨" in s.get("strategy", "")]

    # HTML
    with open("template.html", "r", encoding="utf-8") as f:
        template = Template(f.read())

    html = template.render(
        stocks=sorted_stocks,
        top_stocks=top_names,
        weak_stocks=weak_names,
        rebound_list=", ".join(rebound_list[:5]),
        selloff_list=", ".join(selloff_list[:5])
    )

    now = (datetime.utcnow() + timedelta(hours=8)).strftime("%m%d%H%M")
    filename = f"持股_{now}.html"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("輸出:", filename)
         

    # HTML
    with open("template.html", "r", encoding="utf-8") as f:
        template = Template(f.read())

    html = template.render(
        stocks=sorted_stocks,
        top_stocks=top_names,
        weak_stocks=weak_names,
        rebound_list=", ".join(rebound_list[:5]),
        selloff_list=", ".join(selloff_list[:5])
    )

    now = (datetime.utcnow() + timedelta(hours=8)).strftime("%m%d%H%M")
    filename = f"持股_{now}.html"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("輸出:", filename)


# =========================
# LINE🔥
# =========================
    try:
        from line_push import send_line

        top5 = [f"{s['name']}({s['chgPct']}%)" for s in sorted_stocks[:5]]
        weak5 = [f"{s['name']}({s['chgPct']}%)" for s in sorted_stocks[-5:]]

        msg = f"""
📊 台股技術分析

🔥 強勢股
{chr(10).join(top5)}

⚠ 弱勢股
{chr(10).join(weak5)}

📎 https://nicole0101.github.io/StockHolding-report/
"""

        send_line(msg.strip())

    except Exception as e:
        print("LINE錯誤:", e)


if __name__ == "__main__":
    main()
