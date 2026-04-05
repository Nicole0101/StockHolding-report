import pandas as pd
from datetime import datetime, timedelta
from jinja2 import Template
import os
from data import get_full_stock_analysis  # 確保 data.py 已準備好

# ========================
# 1️⃣ 工具函數：資料結構化整理
# ========================
def format_output(results):
    """將原始分析結果進行過濾、評分與多維度排序"""
    # 1. 過濾掉無效資料
    results = [r for r in results if r and r.get("price")]

    # 2. 計算評分 (Score) 邏輯：綜合殖利率、預估 EPS 與本益比
    for r in results:
        # 確保數值存在，若為 "-" 則視為 0
        y = r.get("yield") if isinstance(r.get("yield"), (int, float)) else 0
        e = r.get("eps_est") if isinstance(
            r.get("eps_est"), (int, float)) else 0
        p = r.get("per_est") if isinstance(
            r.get("per_est"), (int, float)) else 0

        r["score"] = round((y * 2) + (e * 0.5) - (p * 0.3), 2)

    # 3. 執行多重排序
    sorted_by_score = sorted(results, key=lambda x: x["score"], reverse=True)
    sorted_by_chg = sorted(results, key=lambda x: x["chgPct"], reverse=True)

    return {
        "stocks": sorted_by_score,
        "top_stocks": sorted_by_score[:5],   # 評分最高前5
        "hot_stocks": sorted_by_chg[:5],     # 漲幅最高前5
        "weak_stocks": sorted_by_chg[-5:],   # 跌幅最高前5
        "rebound_list": [s for s in results if "反彈" in s.get("strategy", "")],
        "selloff_list": [s for s in results if "出貨" in s.get("strategy", "")],
    }


def build_strings(data):
    """將列表物件轉換為 HTML/LINE 使用的純文字字串"""
    def safe_join(lst):
        return ", ".join([s["name"] for s in lst if s])

    return {
        "top_str": safe_join(data["top_stocks"]),
        "weak_str": safe_join(data["weak_stocks"]),
        "rebound_str": safe_join(data["rebound_list"][:5]),
        "selloff_str": safe_join(data["selloff_list"][:5]),
    }

# ========================
# 2️⃣ 主流程
# ========================


def main():
    # 1. 讀取清單與執行分析
    try:
        df = pd.read_csv("stocks.csv", sep="\t", encoding="utf-8-sig")
        stock_list = df.rename(
            columns={"Ticker": "stock_id", "Name": "name"}
        ).to_dict(orient="records")
    except Exception as e:
        print(f"❌ 讀取 stocks.csv 失敗: {e}")
        return

    print("🚀 開始分析股票...")
    results = get_full_stock_analysis(stock_list)

    if not results:
        print("⚠️ 無分析結果")
        return

    # 2. 格式化資料與時間處理
    data = format_output(results)
    text_data = build_strings(data)

    now_dt = datetime.utcnow() + timedelta(hours=8)
    now_str = now_dt.strftime("%m%d%H%M")
    filename = f"持股_{now_str}.html"

    # 3. 設定 GitHub Pages 連結
    user = "nicole0101"
    repo_name = "StockHolding-report"
    file_url = f"https://{user}.github.io/{repo_name}/{filename}"

    # 4. 渲染 HTML (修正了您原本多出的括號錯誤)
    try:
        with open("template.html", "r", encoding="utf-8") as f:
            template = Template(f.read())

        html_content = template.render(
            stocks=data["stocks"],
            top_stocks=text_data["top_str"],
            weak_stocks=text_data["weak_str"],
            rebound_list=text_data["rebound_str"],
            selloff_list=text_data["selloff_str"],
            generated_time=now_dt.strftime("%Y-%m-%d %H:%M")
        )

        # 寫入當前檔案與 index.html
        for f_name in [filename, "index.html"]:
            with open(f_name, "w", encoding="utf-8") as f:
                f.write(html_content)
        print(f"✅ HTML 已生成：{filename}")

    except Exception as e:
        print(f"❌ HTML 渲染失敗: {e}")

    # 5. 發送 LINE 通知
    send_line_notify(data, file_url)

# ========================
# 3️⃣ LINE 通知模組
# ========================


def send_line_notify(data, file_url):
    """獨立發送 LINE 訊息"""
    try:
        from line_push import send_line

        # 這裡改用評分最高 (Score) 的前五名作為強勢股推薦
        top5_str = "\n".join(
            [f"{s['name']}(評分:{s['score']})" for s in data["top_stocks"]]
        )

        msg = f"""
📊 台股價值投資分析報告

🔥 綜合評分最高 (Top 5):
{top5_str}

📎 完整詳細報表：
{file_url}
        """
        send_line(msg.strip())
        print("✅ LINE 通知已發送")
    except Exception as e:
        print(f"⚠️ LINE 通知發送失敗: {e}")


if __name__ == "__main__":
    main()
