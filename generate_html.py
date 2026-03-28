import pandas as pd
from data import get_stock_data
from indicator import add_indicators
from ai_analysis import analyze
from jinja2 import Template

# ===== 讀取你的持股 CSV =====
def load_stock_list():
    df = pd.read_csv("stocks.csv", sep="\t")
    # 去除欄位空白（防炸）
    df.columns = df.columns.str.strip()
    df = df.rename(columns={
        "Ticker": "stock_id",
        "Name": "name"
    })
    print("欄位:", df.columns.tolist())  # debug
    return df.to_dict(orient="records")
stock_list = load_stock_list()
results = []

# ===== 主迴圈 =====
for s in stock_list:
    code = str(s["stock_id"])
    name = s["name"]

    print(f"處理中: {code} {name}")

    try:
        df = get_stock_data(code)
        df = add_indicators(df)

        latest = df.iloc[-1]

        results.append({
            "name": name,
            "code": code,
            "price": round(latest['close'], 2),
            "k": round(latest['K'], 1),
            "d": round(latest['D'], 1),
            "analysis": analyze(name)
        })

    except Exception as e:
        print(f"錯誤: {code} - {e}")

# ===== 產生 HTML =====
with open("template.html", "r", encoding="utf-8") as f:
    template = Template(f.read())

html = template.render(stocks=results)

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)

print("✅ 報告生成完成")
