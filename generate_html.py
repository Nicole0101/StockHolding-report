import pandas as pd
from data import get_stock_data
from indicator import add_indicators
from jinja2 import Template
from datetime import datetime, timedelta
from FinMind.data import DataLoader

api = DataLoader()

# ================================
# EPS CACHE（效能優化🔥）
# ================================
eps_cache = {}

def estimate_eps(stock_id):
    if stock_id in eps_cache:
        return eps_cache[stock_id]

    try:
        # === EPS ===
        eps_df = api.taiwan_stock_eps(stock_id=stock_id)
        if eps_df is None or eps_df.empty:
            return None, None

        eps_df = eps_df.sort_values("date", ascending=False).head(4)
        if len(eps_df) < 4:
            return None, None

        ttm_eps = eps_df["eps"].astype(float).sum()

        # === 營收 ===
        rev = api.taiwan_stock_month_revenue(stock_id=stock_id)
        if rev is None or rev.empty:
            result = (round(ttm_eps, 2), round(ttm_eps, 2))
            eps_cache[stock_id] = result
            return result

        rev = rev.sort_values("date")
        rev["YoY"] = rev["revenue"].astype(float).pct_change(12)

        growth_series = rev["YoY"].dropna().tail(3)
        growth = growth_series.mean() if len(growth_series) > 0 else 0

        # 防極端值
        growth = max(min(growth, 1.0), -0.5)

        estimated_eps = ttm_eps * (1 + growth)

        result = (round(ttm_eps, 2), round(estimated_eps, 2))
        eps_cache[stock_id] = result
        return result

    except Exception as e:
        print(f"[EPS ERROR] {stock_id}: {e}")
        return None, None


# ================================
# 工具函數
# ================================
def calc_distance(price, ma):
    if ma is None or ma == 0:
        return None
    return round((price - ma) / ma * 100, 2)

def get_signal(k, d):
    if k > 70 and d > 70:
        return "sell"
    elif k < 30 and d < 30:
        return "buy"
    elif k > d:
        return "hold"
    else:
        return "watch"

def get_bb_position(price, upper, lower):
    if price >= upper:
        return "上軌"
    elif price <= lower:
        return "下軌"
    return "中軌"


# ================================
# 單一股票處理（核心🔥）
# ================================
def process_stock(s):
    try:
        stock_id = str(s["stock_id"])

        df = get_stock_data(stock_id)
        df = add_indicators(df)

        if df is None or len(df) < 60:
            return None

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # ===== 價格 =====
        chg = latest["close"] - prev["close"]
        chgPct = (chg / prev["close"]) * 100

        # ===== 震幅 =====
        amp = ((latest["high"] - latest["low"]) / prev["close"]) * 100

        # ===== 均線 =====
        ma20 = df["close"].rolling(20).mean().iloc[-1]
        ma60 = df["close"].rolling(60).mean().iloc[-1]

        dist20 = calc_distance(latest["close"], ma20)
        dist60 = calc_distance(latest["close"], ma60)

        # ===== KD =====
        k = latest["K"]
        d = latest["D"]

        # ===== EPS =====
        ttm_eps, est_eps = estimate_eps(stock_id)

        if ttm_eps is None:
            eps_tag = "無資料"
        elif est_eps > ttm_eps * 1.2:
            eps_tag = "成長🔥"
        elif est_eps < ttm_eps * 0.9:
            eps_tag = "轉弱⚠"
        else:
            eps_tag = "穩定📊"

        # ===== 技術策略 =====
        if amp > 5 and k < 30:
            strategy = "反彈🔥"
        elif amp > 5 and k > 70:
            strategy = "出貨⚠"
        elif amp < 2:
            strategy = "整理"
        else:
            strategy = "觀察"

        # ===== 綜合策略（🔥核心）=====
        if strategy == "反彈🔥" and eps_tag == "成長🔥":
            final_tag = "強勢反彈🚀"
        elif strategy == "出貨⚠" and eps_tag == "轉弱⚠":
            final_tag = "主力出貨💀"
        else:
            final_tag = strategy

        return {
            "name": s["name"],
            "code": stock_id,
            "price": round(latest["close"], 2),
            "chg": round(chg, 2),
            "chgPct": round(chgPct, 2),
            "amp": round(amp, 2),
            "dist20": dist20,
            "dist60": dist60,
            "k": round(k, 1),
            "d": round(d, 1),
            "bb": get_bb_position(latest["close"], latest["BB_upper"], latest["BB_lower"]),
            "sig": get_signal(k, d),

            # 🔥 EPS
            "ttm_eps": ttm_eps,
            "est_eps": est_eps,
            "eps_tag": eps_tag,

            # 🔥 最終策略
            "strategy": final_tag
        }

    except Exception as e:
        print(f"錯誤 {s['stock_id']}:", e)
        return None


# ================================
# 主流程
# ================================
def main():

    df = pd.read_csv("stocks.csv", sep="\t", encoding="utf-8-sig")
    df = df.rename(columns={"Ticker": "stock_id", "Name": "name"})
    stock_list = df.to_dict(orient="records")

    # ===== 批次處理 =====
    results = []
    for s in stock_list:
        data = process_stock(s)
        if data:
            results.append(data)

    print("結果數量:", len(results))

    # ================================
    # 排序（策略優先🔥）
    # ================================
    priority = {
        "強勢反彈🚀": 5,
        "反彈🔥": 4,
        "觀察": 3,
        "整理": 2,
        "出貨⚠": 1,
        "主力出貨💀": 0
    }

    sorted_stocks = sorted(
        results,
        key=lambda x: (priority.get(x["strategy"], 0), x["chgPct"]),
        reverse=True
    )

    # ===== Top / Weak =====
    top_names = ", ".join([s["name"] for s in sorted_stocks[:5]])
    weak_names = ", ".join([s["name"] for s in sorted_stocks[-5:]])

    # ===== 策略統計 =====
    rebound_list = [s["name"] for s in results if "反彈" in s["strategy"]]
    selloff_list = [s["name"] for s in results if "出貨" in s["strategy"]]

    # ================================
    # HTML
    # ================================
    with open("template.html", "r", encoding="utf-8") as f:
        template = Template(f.read())

    html = template.render(
        stocks=sorted_stocks,
        top_stocks=top_names,
        weak_stocks=weak_names,
        rebound_list=", ".join(rebound_list[:5]),
        selloff_list=", ".join(selloff_list[:5])
    )

    # ================================
    # 存檔
    # ================================
    now = (datetime.utcnow() + timedelta(hours=8)).strftime("%m%d%H%M")
    filename = f"持股_{now}.html"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("輸出:", filename)

    # ================================
    # LINE
    # ================================
    from line_push import send_line

    msg = f"""
📊 台股策略分析

🔥 強勢股：
{top_names}

⚠ 弱勢股：
{weak_names}

📌 反彈：
{", ".join(rebound_list[:5])}

📌 出貨：
{", ".join(selloff_list[:5])}

👉 https://nicole0101.github.io/StockHolding-report/
"""

    send_line(msg.strip())


# ================================
# 執行
# ================================
if __name__ == "__main__":
    main()
