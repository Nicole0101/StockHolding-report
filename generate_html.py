import pandas as pd
import config
from datetime import datetime, timedelta
from jinja2 import Template
import os
from data import get_full_stock_analysis  # 確保 data.py 已準備好

# ========================
# 1️⃣ 工具函數：資料結構化整理
# ========================


def format_output(results):
    results = [r for r in results if r and r.get("price")]

    for r in results:
        # ✅ 修正 yield
        y = 0
        if isinstance(r.get("yield"), dict):
            y = r["yield"].get("yield", 0)
        elif isinstance(r.get("yield"), (int, float)):
            y = r["yield"]

        e = r.get("eps_est") if isinstance(
            r.get("eps_est"), (int, float)) else 0
        p = r.get("per_est") if isinstance(
            r.get("per_est"), (int, float)) else 0

        #   r["score"] = round((y * 2) + (e * 0.5) - (p * 0.3), 2)

    sorted_by_score = sorted(results, key=lambda x: x["score"], reverse=True)
    sorted_by_chg = sorted(results, key=lambda x: x["chgPct"], reverse=True)

    return {
        "stocks": sorted_by_chg,
        "top_stocks": sorted_by_score[:5],   # ✅ 修回來
        "hot_stocks": sorted_by_chg[:5],
        "weak_stocks": sorted_by_chg[-5:],
        "rebound_list": [s for s in results if "反彈" in s.get("strategy", "")],
        "selloff_list": [s for s in results if "出貨" in s.get("strategy", "")],
        "buy_signal_list": [s for s in results if s.get("sig") == 1],
        "volume_up_list": [s for s in results if s.get("volume_ok")],
        "bottom_pick_list": [s for s in results if s.get("entry_note") == "抄底"]
    }


def build_strings(data):
    def safe_join(lst):
        return ", ".join([s["name"] for s in lst if s])

    return {
        "top_str": safe_join(data.get("top_stocks", [])),
        "weak_str": safe_join(data.get("weak_stocks", [])),
        "rebound_str": safe_join(data.get("rebound_list", [])[:5]),
        "selloff_str": safe_join(data.get("selloff_list", [])[:5]),
    }


# ========================
# 2️⃣ 主流程
# ========================
def main():
    # 1. 讀取清單與執行分析
    try:
         with open("config.yml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        report_type = config["REPORT_TYPE"]
        csv_file = config["CSV_FILE"]
        report_title = config["REPORT_TITLE"]
        output_file = config["OUTPUT_FILE"]

        df = pd.read_csv(csv_file, sep="\t", encoding="utf-8-sig")
    

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
    print("stock keys:", data["stocks"][0].keys() if data["stocks"] else [])
    now_dt = datetime.utcnow() + timedelta(hours=8)
    now_str = now_dt.strftime("%m%d%H%M")
    filename = f"OUTPUT_FILE_{now_str}.html"

    # 3. 設定 GitHub Pages 連結
    repo_full = os.getenv("GITHUB_REPOSITORY",
                          "nicole0101/Holding")
    branch = os.getenv("GITHUB_REF_NAME", "main")

    # 拆 user / repo
    user, repo = repo_full.split("/")

    # ===== 檔名 =====
    now = (datetime.utcnow() + timedelta(hours=8)).strftime("%m%d%H%M")
    filename = f"{output_file}_{now_str}.html"


    # ===== URL =====
    if branch == "main":
        file_url = f"https://{user}.github.io/{repo}/{filename}"
    else:
        file_url = f"https://github.com/{user}/{repo}/blob/{branch}/{filename}"

    # 4. HTML
    try:
        with open("template.html", "r", encoding="utf-8") as f:
            template = Template(f.read())

        html_content = template.render(
            stocks=data["stocks"],
            top_stocks=text_data["top_str"],
            weak_stocks=text_data["weak_str"],
            rebound_list=text_data["rebound_str"],
            selloff_list=text_data["selloff_str"],
            report_title=report_title
        )
        
        # 寫入當前檔案與 index.html
        for f_name in [filename, "index.html"]:
            with open(f_name, "w", encoding="utf-8") as f:
                f.write(html_content)
        print(f"✅ HTML 已生成：{filename}")

    except Exception as e:
        print(f"❌ HTML 生成失敗: {e}")

    # 5. 發送 LINE 通知
    send_line_notify(data, file_url, report_title, report_type)


# ========================
# 3️⃣ LINE 通知模組
# ========================
def send_line_notify(data, file_url):
    """獨立發送 LINE 訊息"""
    try:
        from line_push import send_line
        stocks = data.get("stocks", [])
        top5 = [f"{s['name']}({s['chgPct']}%)" for s in stocks[:5]]
        weak5 = [f"{s['name']}({s['chgPct']}%)" for s in stocks[-5:]]
        msg = f"""

📊 (持股)價值投資分析報告

🔥 強勢股
{chr(10).join(top5)}

⚠ 弱勢股
{chr(10).join(weak5)}
📎 {file_url}

📎 完整詳細報表：
{file_url}
        """
        send_line(msg.strip())
        print("✅ LINE 通知已發送")
    except Exception as e:
        print(f"⚠️ LINE 通知發送失敗: {e}")


if __name__ == "__main__":
    main()
