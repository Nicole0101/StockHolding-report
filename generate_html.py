import pandas as pd
import requests 
from data import get_stock_data
from indicator import add_indicators
from jinja2 import Template
from datetime import datetime, timedelta
import os

API_TOKEN ="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMy0yOCAyMjo0Mzo0NiIsInVzZXJfaWQiOiJuaWNvbGUwMTAxIiwiZW1haWwiOiJuaWNvbGVfbGluQG1zbi5jb20iLCJpcCI6IjM2LjIyNC4yNTMuMjUifQ.bjWqLj9jmNvMA75Jx6H88FhDWh0D1rHVOkVsndXgboA"   # ⭐ 直接寫這裡
print("FINMIND_TOKEN:", API_TOKEN)    
def get_TWSE_data():
    url = "https://api.finmindtrade.com/api/v4/data"

    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": "TAIEX",   # 確保是這個
        "start_date": "2024-01-01",
        "token": API_TOKEN
    }

    res = requests.get(url, params=params)
    data = res.json()

    return pd.DataFrame(data.get("data", []))
    

# ===== 讀CSV =====
def load_stock_list():
    df = pd.read_csv("stocks.csv", sep="\t", encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    df = df.rename(columns={
        "Ticker": "stock_id",
        "Name": "name"
    })
    return df.to_dict(orient="records")

# ===== 簡單判斷邏輯（讓UI會動🔥）=====
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
    elif price > (upper + lower) / 2:
        return "中軌上方"
    else:
        return "中軌下方"


# ===== 主流程 =====
stock_list = load_stock_list()
results = []

for s in stock_list:
    try:
        code = str(s["stock_id"])
        name = s["name"]
        #    print(f"處理中: {code}")

        df = get_stock_data(code)
        df = add_indicators(df)
        if df.empty:
            continue

        latest = df.iloc[-1]
        prev = df.iloc[-2]
        chg = latest['close'] - prev['close']
        chgPct = (chg / prev['close']) * 100
        amplitude = ((latest['high'] - latest['low']) / latest['close']) * 100
        
        k = round(latest['K'], 1)
        d = round(latest['D'], 1)

        signal = get_signal(k, d)

        bb = get_bb_position(
            latest['close'],
            latest['BB_upper'],
            latest['BB_lower']
        )

        results.append({          
            "name": name,
            "code": code,
            "price": round(latest['close'], 2),
            
            "chg": round(chg, 2),
            "chgPct": round(chgPct, 2),
            "amp": round(amplitude, 2),
            
            "kPat": "整理",
            "k": k,
            "d": d,
            "kdDiv": "無背離",
            "bb": bb,
            "bbW": "正常",
            "sig": signal        
        })

    except Exception as e:
        print(f"錯誤: {s} - {e}")
print("結果數量:",len(results))
# ===== 強弱股 =====
sorted_stocks = sorted(results, key=lambda x: x["chgPct"], reverse=True)

top_stocks = sorted_stocks[:5]
weak_stocks = sorted_stocks[-5:]

top_names = ", ".join([s["name"] for s in top_stocks])
weak_names = ", ".join([s["name"] for s in weak_stocks])
# ===== AI盤勢判讀 =====
buy_count = sum(1 for s in results if s["sig"] == "buy")
sell_count = sum(1 for s in results if s["sig"] == "sell")

if chg_pct > 1:
    trend = "強勢上攻"
elif chg_pct > 0:
    trend = "震盪偏多"
elif chg_pct < -1:
    trend = "明顯走弱"
else:
    trend = "震盪整理"

ai_summary = f"""
📊 台股盤勢分析

今日大盤呈現「{trend}」，指數變動 {round(chg_pct,2)}%。

📈 強勢族群：{strong_sector}
📉 弱勢族群：{weak_sector}

🔥 強勢股：{top_names}
⚠ 弱勢股：{weak_names}

📊 籌碼結構：
買進訊號 {buy_count} 檔，賣出訊號 {sell_count} 檔

📌 操作建議：
短線可關注強勢族群，避免弱勢股追價。
"""
# ===== 讀大盤 =====  
TWSE = get_TWSE_data()
if API_TOKEN is None:
    print("沒有設定 FinMind TOKEN")
    TWSE = None

if TWSE is None or TWSE.empty or len(TWSE) < 2:
    print("⚠️ 大盤資料為空，使用預設值")
    index_value = 0
    chg = 0
    chg_pct = 0
    market_trend = "資料不足"
    summary_text = "⚠️ 無法取得台股資料（請檢查 TOKEN）"

else:
    latest = TWSE.iloc[-1]
    prev = TWSE.iloc[-2]

    index_value = latest["close"]
    chg = latest["close"] - prev["close"]
    chg_pct = (chg / prev["close"]) * 100

    market_trend = "偏多 📈" if chg_pct > 0 else "偏空 📉"

    summary_text = f"""
加權指數：{round(index_value,2)}
漲跌：{round(chg,2)} ({round(chg_pct,2)}%)
盤勢：{market_trend}
"""

# ===== 產HTML =====
with open("template.html", "r", encoding="utf-8") as f:
    template = Template(f.read())
    html = template.render(
    stocks=results,
    market={
        "index": round(index_value, 2),
        "chg": round(chg, 2),
        "chg_pct": round(chg_pct, 2),
        "trend": market_trend
    },
    summary=summary_text
)

# 使用統一的時間（UTC+8）
now = (datetime.utcnow() + timedelta(hours=8)).strftime("%m%d%H%M")
filename = f"持股_{now}.html"

# ===== 產生歷史檔 ===== 
with open(filename, "w", encoding="utf-8") as f:
    f.write(html)

# ===== 更新首頁 ===== 
with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)

print("輸出檔案:", filename)

# ===== 清理舊檔（只留最新3份）=====
files = [f for f in os.listdir() if f.startswith("持股_") and f.endswith(".html")]
files.sort(reverse=True)
for f in files[3:]:
    os.remove(f)
    print("刪除舊檔:", f)

# ===== LINE 推播 =====
from line_push import send_line
buy_count = sum(1 for s in results if s["sig"] == "buy")
sell_count = sum(1 for s in results if s["sig"] == "sell")
hold_count = sum(1 for s in results if s["sig"] == "hold")
watch_count = sum(1 for s in results if s["sig"] == "watch")
if buy_count > sell_count:
    market = "偏多 📈"
elif sell_count > buy_count:
    market = "偏空 📉"
else:
    market = "震盪 🤝"
msg = (
    f"📊 台股盤後分析\n\n"
    f"盤勢：{market}\n\n"
    f"買進：{buy_count}\n"
    f"賣出：{sell_count}\n"
    f"觀察：{watch_count}\n"
    f"中立：{hold_count}\n\n"
    f"👉 https://Nicole0101.github.io/StockHolding-report/"
)
send_line("msg")
