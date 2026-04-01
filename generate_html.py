import pandas as pd
from jinja2 import Template
from datetime import datetime, timedelta

# =========================
# 模擬資料來源（防止爆）
# 👉 你可替換成 process_stock
# =========================
def get_results_safe():
    try:
        df = pd.read_csv("stocks.csv", sep="\t", encoding="utf-8-sig")
        df = df.rename(columns={"Ticker": "stock_id", "Name": "name"})
        stock_list = df.to_dict(orient="records")

        results = []

        for s in stock_list:
            try:
                # 👉 這裡可以接你的 process_stock()
                results.append({
                    "name": s["name"],
                    "code": s["stock_id"],
                    "chgPct": 0,
                    "strategy": "觀察"
                })
            except Exception as e:
                print(f"單股錯誤 {s['stock_id']}:", e)

        return results

    except Exception as e:
        print("讀取 stocks.csv 失敗:", e)
        return []


# =========================
# 主程式（穩定版🔥）
# =========================
def main():

    # ===== 安全取得資料 =====
    results = get_results_safe()

    if not results:
        print("⚠️ 無資料，使用空報表")

    # ===== 排序（安全）=====
    priority = {
        "強勢反彈🚀": 5,
        "反彈🔥": 4,
        "觀察": 3,
        "整理": 2,
        "出貨⚠": 1,
        "主力出貨💀": 0
    }

    try:
        sorted_stocks = sorted(
            results,
            key=lambda x: (
                priority.get(x.get("strategy", ""), 0),
                x.get("chgPct", 0)
            ),
            reverse=True
        )
    except Exception as e:
        print("排序錯誤:", e)
        sorted_stocks = results

    # ===== Top / Weak（防空）=====
    top_names = ", ".join([s["name"] for s in sorted_stocks[:5]]) if sorted_stocks else "-"
    weak_names = ", ".join([s["name"] for s in sorted_stocks[-5:]]) if sorted_stocks else "-"

    rebound_list = [s["name"] for s in results if "反彈" in s.get("strategy", "")]
    selloff_list = [s["name"] for s in results if "出貨" in s.get("strategy", "")]

    # ===== HTML（防 template 爆）=====
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
        print("HTML 渲染錯誤:", e)
        html = "<h1>報表產生失敗</h1>"

    # ===== 存檔（防寫入錯）=====
    try:
        now = (datetime.utcnow() + timedelta(hours=8)).strftime("%m%d%H%M")
        filename = f"持股_{now}.html"

        with open(filename, "w", encoding="utf-8") as f:
            f.write(html)

        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html)

        print("輸出:", filename)

    except Exception as e:
        print("寫檔錯誤:", e)


# =========================
# 執行
# =========================
if __name__ == "__main__":
    main()


# ===== LINE 專業版推播 =====
try:
    from line_push import send_line

    # 🔥 訊號統計
    buy_count = sum(1 for s in results if s.get("sig") == "buy")
    sell_count = sum(1 for s in results if s.get("sig") == "sell")
    watch_count = sum(1 for s in results if s.get("sig") == "watch")
    hold_count = sum(1 for s in results if s.get("sig") == "hold")

    # 🔥 市場判斷（用策略推估）
    if buy_count > sell_count:
        market = "偏多 📈"
    elif sell_count > buy_count:
        market = "偏空 📉"
    else:
        market = "震盪 🤝"

    # 🔥 強弱股
    top5 = [f"{s['name']}({s['chgPct']}%)" for s in sorted_stocks[:5]]
    weak5 = [f"{s['name']}({s['chgPct']}%)" for s in sorted_stocks[-5:]]

    # 🔥 策略
    rebound = [s["name"] for s in results if "反彈" in s.get("strategy", "")]
    selloff = [s["name"] for s in results if "出貨" in s.get("strategy", "")]

    # =========================
    # 📊 專業版訊息
    # =========================
    msg = f"""
📊 台股技術分析報告（盤後）

━━━━━━━━━━━━━━━
📈 市場狀態：{market}

🧭 訊號分布
買進：{buy_count} ｜ 賣出：{sell_count}
觀察：{watch_count} ｜ 中立：{hold_count}

━━━━━━━━━━━━━━━
🔥 強勢股 TOP5
{chr(10).join(top5)}

⚠ 弱勢股 TOP5
{chr(10).join(weak5)}

━━━━━━━━━━━━━━━
📌 交易策略

🔥 反彈機會：
{", ".join(rebound[:5]) if rebound else "無"}

⚠ 出貨警示：
{", ".join(selloff[:5]) if selloff else "無"}

━━━━━━━━━━━━━━━
📎 完整報告
https://nicole0101.github.io/StockHolding-report/

（自動生成）
"""

    send_line(msg.strip())

except Exception as e:
    print("LINE發送失敗:", e)
