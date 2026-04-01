import pandas as pd
from jinja2 import Template
from datetime import datetime, timedelta

# =========================
# 資料來源（安全版）
# =========================
def get_results_safe():
    try:
        df = pd.read_csv("stocks.csv", sep="\t", encoding="utf-8-sig")
        df = df.rename(columns={"Ticker": "stock_id", "Name": "name"})
        stock_list = df.to_dict(orient="records")

        results = []

        for s in stock_list:
            results.append({
                "name": s["name"],
                "code": s["stock_id"],
                "chgPct": 0,
                "strategy": "觀察",
                "sig": "hold"
            })

        return results

    except Exception as e:
        print("讀取 stocks.csv 失敗:", e)
        return []


# =========================
# 主程式（🔥全部集中）
# =========================
def main():

    # ===== 資料 =====
    results = get_results_safe()

    if not results:
        print("⚠️ 無資料")

    # ===== 排序 =====
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
        key=lambda x: (
            priority.get(x.get("strategy", ""), 0),
            x.get("chgPct", 0)
        ),
        reverse=True
    )

    # ===== Top / Weak =====
    top_names = ", ".join([s["name"] for s in sorted_stocks[:5]]) if sorted_stocks else "-"
    weak_names = ", ".join([s["name"] for s in sorted_stocks[-5:]]) if sorted_stocks else "-"

    rebound_list = [s["name"] for s in results if "反彈" in s.get("strategy", "")]
    selloff_list = [s["name"] for s in results if "出貨" in s.get("strategy", "")]

    # ===== HTML =====
    try:
        with open("template.html", "r", encoding="utf-8") as f:
            template = Template(f.read())

        html = template.render(
            stocks=sorted_stocks,
            top_stocks=top_names,
            weak_stocks=weak_names,
            rebound_list=", ".join(rebound_list[:5]) if rebound_list else "-",
            selloff_list=", ".join(selloff_list[:5]) if selloff_list else "-"
        )

    except Exception as e:
        print("HTML錯誤:", e)
        html = "<h1>HTML ERROR</h1>"

    # ===== 存檔 =====
    now = (datetime.utcnow() + timedelta(hours=8)).strftime("%m%d%H%M")
    filename = f"持股_{now}.html"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("輸出:", filename)

    # =========================
    # 🔥 LINE（修正重點🔥）
    # =========================
    try:
        from line_push import send_line

        buy_count = sum(1 for s in results if s.get("sig") == "buy")
        sell_count = sum(1 for s in results if s.get("sig") == "sell")
        watch_count = sum(1 for s in results if s.get("sig") == "watch")
        hold_count = sum(1 for s in results if s.get("sig") == "hold")

        if buy_count > sell_count:
            market = "偏多 📈"
        elif sell_count > buy_count:
            market = "偏空 📉"
        else:
            market = "震盪 🤝"

        top5 = [f"{s['name']}({s['chgPct']}%)" for s in sorted_stocks[:5]]
        weak5 = [f"{s['name']}({s['chgPct']}%)" for s in sorted_stocks[-5:]]

        msg = f"""
📊 台股技術分析報告

━━━━━━━━━━━━━━━
📈 市場狀態：{market}

🧭 訊號
買:{buy_count} 賣:{sell_count}
觀:{watch_count} 中:{hold_count}

━━━━━━━━━━━━━━━
🔥 強勢股
{chr(10).join(top5)}

⚠ 弱勢股
{chr(10).join(weak5)}

━━━━━━━━━━━━━━━
📎 報告
https://nicole0101.github.io/StockHolding-report/
"""

        send_line(msg.strip())

    except Exception as e:
        print("LINE發送失敗:", e)


# =========================
# 執行
# =========================
if __name__ == "__main__":
    main()
