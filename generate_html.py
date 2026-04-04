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
            "start_date": "2020-01-01",
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
        # ===== 可能的現金股利欄位 =====
        cash_cols = [
            "CashEarningsDistribution",
            "CashStatutorySurplus"
        ]

        exist_cols = [c for c in cash_cols if c in df.columns]

        if not exist_cols:
            print("❌ 沒有現金股利欄位", stock_id)
            return None

        # ===== 轉數值 =====
        for col in exist_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df["year"] = pd.to_numeric(df["year"], errors="coerce")

        # ===== 同一年加總（關鍵🔥）=====
        df_group = df.groupby("year")[exist_cols].sum().reset_index()

        # 合併成一欄
        df_group["cash_dividend"] = df_group[exist_cols].sum(axis=1)

        # ===== 排序（最新在前）=====
        df_group = df_group.sort_values("year", ascending=False)
        print("df_group.head: ", df_group.head())
        # ===== 找最近有配息 =====
        for _, row in df_group.iterrows():
            if row["cash_dividend"] > 0:
                print("抓到股利:", stock_id, row["year"], row["cash_dividend"])
                return round(row["cash_dividend"], 2)

        return None
        print("DIV TABLE", stock_id)

    except Exception as e:
        print(f"股利錯誤: {stock_id}", e)
        return None
# ======================


def get_yield(stock_id):
    try:
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {
            "dataset": "TaiwanStockPER",
            "data_id": stock_id,
            "start_date": "2023-01-01",
            "token": FINMIND_TOKEN
        }
        res = requests.get(url, params=params)
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

# ===============================================


def get_eps(stock_id):
    try:
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {
            "dataset": "TaiwanStockFinancialStatements",
            "data_id": stock_id,
            "start_date": "2023-01-01",
            "token": FINMIND_TOKEN
        }

        data = requests.get(url, params=params).json().get("data", [])
        if not data:
            return None

        df = pd.DataFrame(data)
        df = df[df["type"] == "EPS"]

        if df.empty:
            return None

        df["date"] = pd.to_datetime(df["date"])
        df["year"] = df["date"].dt.year
        df["season"] = df["date"].dt.quarter
        df["value"] = pd.to_numeric(df["value"], errors="coerce")

        last_year = datetime.now().year - 1
        df = df[df["year"] == last_year]

        if df.empty:
            return None

        # 去重（避免同一季多筆）
        df = df.sort_values("date").drop_duplicates(
            ["year", "season"], keep="last")

        # ===== 正確邏輯 =====
        # 1. 有四季 → 用加總（最準）
        if df["season"].nunique() >= 4:
            return round(df["value"].sum(), 2)

        # 2. fallback：只有Q4（有些公司會累計）
        q4 = df[df["season"] == 4]
        if not q4.empty:
            val = q4.sort_values("date")["value"].iloc[-1]
            # 保護：避免把單季當全年（例如 < 4 通常是單季）
            if val > 4:  # 可依需求調整
                return round(val, 2)
        return None
        Print("Date EPS: ", df.value)
    except Exception as e:
        print("EPS錯誤:", stock_id, e)
        return None


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


# 指標=========================
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

# 距離（你指定版本）=========================


def calc_dist(price, ma):
    if ma == 0 or pd.isna(ma):
        return None
    return round((price - ma) / ma * 100, 2)


# 單股處理=========================
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
        last_eps = get_eps(s["stock_id"])
        eps_note = ""
        quarters = 0

        # ===== 殖利率 =====
        yield_pct = get_yield(s["stock_id"])
        # print("yield_pct: ", s["stock_id"], yield_pct)

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
        ma6 = df["close"].rolling(6).mean().iloc[-1]
        ma18 = df["close"].rolling(18).mean().iloc[-1]
        ma50 = df["close"].rolling(50).mean().iloc[-1]

        dist6 = calc_dist(latest["close"], ma6)
        dist18 = calc_dist(latest["close"], ma18)
        dist50 = calc_dist(latest["close"], ma50)

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
            "eps_last": f"{last_eps}{eps_note}" if last_eps is not None else "-",
            "yield": f"{yield_pct}" if yield_pct is not None else "-",
            "per": per if per else "-",
            "est_eps": est_eps if est_eps else "-",

            "dist6": dist6,
            "dist18": dist18,
            "dist50": dist50,
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

    rebound_list = [s["name"]
                    for s in results if "反彈" in s.get("strategy", "")]
    selloff_list = [s["name"]
                    for s in results if "出貨" in s.get("strategy", "")]

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
    repo = os.getenv("GITHUB_REPOSITORY", "nicole0101/StockHolding-report")
    branch = os.getenv("GITHUB_REF_NAME", "main")
    user, repo_name = repo.split("/")

    now = (datetime.utcnow() + timedelta(hours=8)).strftime("%m%d%H%M")

    filename = f"持股_{now}.html"

    user = "nicole0101"
    repo = "StockHolding-report"
    # base_url = f"https://{user}.github.io/{repo}/"
    # file_url = base_url + filename
    if branch == "main":
        file_url = f"https://{user}.github.io/{repo}/{filename}"
    else:
        file_url = f"https://github.com/{user}/{repo}/blob/{branch}/{filename}"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

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
📎 {file_url}

📎 https://nicole0101.github.io/StockHolding-report/{filename}
"""

        send_line(msg.strip())

    except Exception as e:
        print("LINE錯誤:", e)


if __name__ == "__main__":
    main()
