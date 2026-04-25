import os
import pandas as pd

base_dir = os.path.dirname(os.path.abspath(__file__))
allcsv_dir = os.path.join(base_dir, "Allcsv")
output_gold = os.path.join(base_dir, "Holding.csv")

all_rows = []

print("cwd =", os.getcwd(), flush=True)
print("script dir =", base_dir, flush=True)
print("allcsv_dir =", allcsv_dir, flush=True)
print("output_gold =", output_gold, flush=True)

if not os.path.isdir(allcsv_dir):
    raise FileNotFoundError(f"Allcsv directory not found: {allcsv_dir}")


def read_csv_flexible(file_path):
    encodings = ["utf-8-sig", "utf-8", "cp950", "big5"]

    last_error = None
    for enc in encodings:
        try:
            df = pd.read_csv(file_path, sep="\t", encoding=enc)

            if len(df.columns) == 1:
                df = pd.read_csv(file_path, encoding=enc)

            return df, enc
        except Exception as e:
            last_error = e

    raise last_error


for filename in os.listdir(allcsv_dir):
    file_path = os.path.join(allcsv_dir, filename)

    if not os.path.isfile(file_path):
        print(f"skip not file: {filename}", flush=True)
        continue

    if not filename.lower().endswith((".csv", ".txt")):
        print(f"skip ext: {filename}", flush=True)
        continue

    try:
        df, used_encoding = read_csv_flexible(file_path)
        df.columns = df.columns.str.strip()

        if {"Ticker", "Name"}.issubset(df.columns):
            temp = df[["Ticker", "Name"]].copy()
        elif {"代碼", "名稱"}.issubset(df.columns):
            temp = df[["代碼", "名稱"]].copy()
            temp.columns = ["Ticker", "Name"]
        else:
            print(
                f"skip columns: {filename}, encoding={used_encoding}, columns={df.columns.tolist()}",
                flush=True
            )
            continue

        temp["Ticker"] = temp["Ticker"].astype(str).str.strip()
        temp["Name"] = temp["Name"].astype(str).str.strip()

        temp = temp[
            (temp["Ticker"] != "") &
            (temp["Name"] != "") &
            (temp["Ticker"].str.lower() != "nan") &
            (temp["Name"].str.lower() != "nan")
        ]

        if not temp.empty:
            all_rows.append(temp)

        print(f"loaded: {filename}, encoding={used_encoding}, rows={len(temp)}", flush=True)

    except Exception as e:
        print(f"failed: {filename}, error={e}", flush=True)

if all_rows:
    result = pd.concat(all_rows, ignore_index=True)
    result["Ticker_num"] = pd.to_numeric(result["Ticker"], errors="coerce")

    result = (
        result
        .drop_duplicates(subset=["Ticker"], keep="first")
        .sort_values(by=["Ticker_num", "Ticker"], ascending=[True, True], na_position="last")
        .drop(columns=["Ticker_num"])
        .reset_index(drop=True)
    )

    result.to_csv(output_gold, sep="\t", index=False, encoding="utf-8-sig")

    print(f"written: {output_gold}", flush=True)
    print(f"rows: {len(result)}", flush=True)
else:
    print("no data", flush=True)
