import os
import requests

TOKEN = os.getenv("LINE_TOKEN")
USER_ID = os.getenv("LINE_USER_ID")

def send_line(msg):
    try:
        url = "https://api.line.me/v2/bot/message/push"
        headers = {
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "to": USER_ID,
            "messages": [
                {
                    "type": "text",
                    "text": msg
                }
            ]
        }
        res = requests.post(url, headers=headers, json=data)
        print("LINE status:", res.status_code)
        print("LINE response:", res.text)
    except Exception as e:
        print("LINE error:", e)    requests.post(url, headers=headers, json=data)

if __name__ == "__main__":
    send_line("📊 今日股票報告已產生")
