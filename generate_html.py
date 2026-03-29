import pandas as pd
import requests 
from data import get_stock_data
from indicator import add_indicators
from jinja2 import Template

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
        print(f"處理中: {code}")

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
print("結果數量:", len(results))

# ===== 產HTML =====
with open("template.html", "r", encoding="utf-8") as f:
    template = Template(f.read())
html = template.render(stocks=results)

from datetime import datetime
now = datetime.now().strftime("%m%d%H%M")
filename = f"持股_{now}.html"

with open(filename, "w", encoding="utf-8") as f:
    f.write(html)

# ===== 同時更新 index.html（給網站用）===== 
from datetime import datetime, timedelta
now = (datetime.utcnow() + timedelta(hours=8)).strftime("%m%d%H%M")
filename = f"持股_{now}.html"
from line_push import send_line
send_line(f"📊 股票報告已產生\n👉 {filename}")
# ===== 產生歷史檔===== 
with open(filename, "w", encoding="utf-8") as f:
    f.write(html)

# ===== 更新首頁===== 
with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)
print("輸出檔案:", filename)

import os
# ===== 清理舊檔（只留最新3份）=====
files = [f for f in os.listdir() if f.startswith("持股_") and f.endswith(".html")]
# 依時間排序（新→舊）
files.sort(reverse=True)
# 保留前3個，其餘刪掉
for f in files[3:]:
    os.remove(f)
    print("刪除舊檔:", f)

# LINE 推播
def send_line_message(msg):
    try:
        url = "https://api.line.me/v2/bot/message/push"
        headers = {
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json"
        }

        data = {
            "to": USER_ID,
            "messages": [
                {"type": "text", "text": msg}
            ]
        }

        res = requests.post(url, headers=headers, json=data)
        print("LINE status:", res.status_code)
    except Exception as e:
        print("LINE 發送失敗:", e)# 發送通知
send_line_message(f"📊 台股報告已更新：{filename}")
send_line_message(f"📊 最新報告\nhttps://Nicole0101.github.io/StockHolding-report/")
