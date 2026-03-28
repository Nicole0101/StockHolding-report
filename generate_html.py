from jinja2 import Template
from data import get_stock_data
from indicator import add_indicators
from ai_analysis import analyze

stocks = ["2330", "2317", "2454"]

results = []

for s in stocks:
    df = get_stock_data(s)
    df = add_indicators(df)

    results.append({
        "code": s,
        "price": df['close'].iloc[-1],
        "analysis": analyze(s)
    })

# 載入模板
with open("template.html", "r", encoding="utf-8") as f:
    template = Template(f.read())

html = template.render(stocks=results)

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)
