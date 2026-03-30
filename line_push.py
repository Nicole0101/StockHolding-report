import os
import requests

TOKEN = os.getenv("LINE_TOKEN")
USER_ID = os.getenv("LINE_USER_ID")
#    TOKEN ="9M5g3pzqJ0od0O9mHpApPXtrIod0a+NBW3Rp7ZymcAK1AkstRaKqCYU0LaYNs3yjihHw2ANnVZcCeQ20froIJ2CnnFJ7tHQp2JC0e0BnXnmSka7BrJqNNyppbG/JO4uJhG2lHPHv/+/EeVYNdDHhWgdB04t89/1O/w1cDnyilFU="
#    USER_ID="Ub255cf0f7742ae1f5947b267afc24024"
print("TOKEN:", TOKEN)
print("USER_ID:", USER_ID)

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
        print("LINE error:", e)


if __name__ == "__main__":
    send_line("📊 今日股票報告已產生")
