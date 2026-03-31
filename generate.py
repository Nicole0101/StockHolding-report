import json

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False)
