import pandas as pd
import requests
from data import get_stock_data
from indicator import add_indicators
from jinja2 import Template
from datetime import datetime, timedelta
import os
import json

# ===== API =====
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
def ask_gpt_json(prompt):
    url = "https://api.openai.com/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "請用JSON格式回覆"},
            {"role": "user", "content": prompt}
        ]
    }

    try:
        res = requests.post(url, headers=headers, json=data)
        result = res.json()

        # 🔥 Debug（很重要）
        print("GPT raw:", result)

        if "choices" not in result:
            print("❌ GPT回傳錯誤:", result)
            return "{}"

        return result["choices"][0]["message"]["content"]

    except Exception as e:
        print("❌ GPT exception:", e)
        return "{}"

# ===== FinMind =====
API_TOKEN = "你的FinMindToken"

def get_TWSE_data():
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": "TAIEX",
        "start_date": "2024-01-01",
        "token": API_TOKEN
    }

    res = requests.get(url, params=params)
    return pd.DataFrame(res.json().get("data", []))


# ===== 讀CSV =====
def load_stock_list():
    df = pd.read_csv("stocks.csv", sep="\t", encoding="utf-8-sig")
    df = df.rename(columns={"Ticker": "stock_id", "Name": "name"})
    return df.to_dict(orient="records")

# ===== 財務 + 技術補充 =====
def estimate_eps(eps_list):
    if not eps_list or len(eps_list) < 4:
        return None
    return round(sum(eps_list), 2)

def calc_bias(price, ma):
    if not ma or ma == 0:
        return None
    return round((price - ma) / ma * 100, 2)



# ===== 技術判斷 =====
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
        return "上軌挑戰"
    elif price <= lower:
        return "下軌測試"
    return "中軌區間"


# ===== 主流程 =====
stock_list = load_stock_list()
results = []

for s in stock_list:
    try:
        df = get_stock_data(str(s["stock_id"]))
        df = add_indicators(df)

        if df is None or len(df) < 2:
            continue

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        chg = latest["close"] - prev["close"]
        chgPct = (chg / prev["close"]) * 100
        amplitude = ((latest['high'] - latest['low']) / prev['close']) * 100


        # ===== 波動策略 =====
        k = latest['K']
        if amplitude > 5 and k < 30:
            strategy = "反彈🔥"
        elif amplitude > 5 and k > 70:
            strategy = "出貨⚠"
        elif amplitude < 2:
            strategy = "整理"
        else:
            strategy = "觀察"
            results.append({
            "name": s["name"],
            "code": s["stock_id"],
            "price": round(latest["close"], 2),
            "chg": round(chg, 2),
            "chgPct": round(chgPct, 2),
            "amp": round(amplitude, 2),
            "strategy": strategy,
            "k": round(latest["K"], 1),
            "d": round(latest["D"], 1),
            "bb": get_bb_position(latest["close"], latest["BB_upper"], latest["BB_lower"]),
            "sig": get_signal(latest["K"], latest["D"])
            "bias_20": bias_20,
            "bias_60": bias_60,
            "eps_4q": eps_list,
            "eps_est": eps_est
        })
    except Exception as e:
        print("錯誤:", e)
print("結果數量:", len(results))

# ===== 波動策略統計（放這裡🔥）=====
rebound_list = [s["name"] for s in results if s.get("strategy") == "反彈🔥"]
selloff_list = [s["name"] for s in results if s.get("strategy") == "出貨⚠"]

# ===== 大盤 =====
TWSE = get_TWSE_data()

if TWSE is None or len(TWSE) < 2:
    chg_pct = 0
    index_value = 0
    market_trend = "資料不足"
else:
    latest = TWSE.iloc[-1]
    prev = TWSE.iloc[-2]

    # ===== 均線 =====
    ma20 = latest.get("MA20")
    ma60 = latest.get("MA60")
    bias_20 = calc_bias(latest["close"], ma20)
    bias_60 = calc_bias(latest["close"], ma60)
    # ===== EPS（先用假資料，之後可接 API）=====
    # TODO: 可改接 FinMind 財報
    eps_list = [
        round(latest.get("eps_q1", 1.2), 2),
        round(latest.get("eps_q2", 1.3), 2),
        round(latest.get("eps_q3", 1.1), 2),
        round(latest.get("eps_q4", 1.4), 2),
    ]
    eps_est = estimate_eps(eps_list)
    
    index_value = latest["close"]
    chg = latest["close"] - prev["close"]
    chg_pct = (chg / prev["close"]) * 100
    market_trend = "偏多 📈" if chg_pct > 0 else "偏空 📉"


# ===== 強弱股 =====
sorted_stocks = sorted(results, key=lambda x: x["chgPct"], reverse=True)
top_names = ", ".join([s["name"] for s in sorted_stocks[:5]])
weak_names = ", ".join([s["name"] for s in sorted_stocks[-5:]])

# ===== GPT 呼叫（含重試）=====
import time

gpt_raw = "{}"

for i in range(3):
    try:
        gpt_raw = ask_gpt_json(prompt)
        if gpt_raw and gpt_raw != "{}":
            break
    except Exception as e:
        print("GPT錯誤:", e)
    time.sleep(2)


# ===== HTML =====
with open("template.html", "r", encoding="utf-8") as f:
    template = Template(f.read())

html = template.render(
    stocks=results,
    market={
        "index": round(index_value, 2),
        "chg_pct": round(chg_pct, 2),
        "trend": market_trend
    },
    top_stocks=top_names,
    weak_stocks=weak_names
)

# ===== 存檔 =====
now = (datetime.utcnow() + timedelta(hours=8)).strftime("%m%d%H%M")
filename = f"持股_{now}.html"
with open(filename, "w", encoding="utf-8") as f:
    f.write(html)
with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)
print("輸出:", filename)

# ===== LINE =====
from line_push import send_line

msg = f"""
📊 台股盤後分析

{gpt_summary or '（無）'}

📈盤勢：{gpt_trend}
🔥強勢族群：{gpt_strong}
⚠弱勢族群：{gpt_weak}

📌 買進：{gpt_buy}
📌 賣出：{gpt_sell}

👉 https://nicole0101.github.io/StockHolding-report/
""".strip()

send_line(msg)
