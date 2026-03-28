import requests
import pandas as pd

def get_stock_data(stock_id):
    url = f"https://query1.finance.yahoo.com/v7/finance/chart/{stock_id}.TW"
    res = requests.get(url).json()

    close = res['chart']['result'][0]['indicators']['quote'][0]['close']
    return pd.DataFrame({"close": close})
