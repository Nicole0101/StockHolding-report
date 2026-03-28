import pandas_ta as ta

def add_indicators(df):
    df['K'], df['D'] = ta.stoch(df['close'], df['close'], df['close'])
    bb = ta.bbands(df['close'])

    df['bb_upper'] = bb['BBU_5_2.0']
    df['bb_lower'] = bb['BBL_5_2.0']

    return df
