from datetime import datetime

import pandas as pd
import requests
import os
import config

from data_sources import get_revenue_raw, get_per_pbr_90d_stats
from financial_analysis import (
    get_eps_analysis,
    get_profit_ratio,
    extract_metric,
)


def get_finmind_usage():
    token = os.getenv("FINMIND_TOKEN")
    headers = {"Authorization": f"Bearer {token}"}
    url = "https://api.web.finmindtrade.com/v2/user_info"
    resp = requests.get(url, headers=headers, timeout=30)
    data = resp.json()
    used = data.get("user_count", 0)
    limit = data.get("api_request_limit", 0)
    remain = limit - used
    print(f"FinMind usage: {used}/{limit}, remain={remain}")
    return used, limit, remain


def get_revenue_trend(stock_id):
    try:
        data = get_revenue_raw(stock_id)
        if not data:
            return None

        df = pd.DataFrame(data)

        if "revenue" not in df.columns:
            if "value" in df.columns:
                df["revenue"] = df["value"]
            else:
                return None

        df["date"] = pd.to_datetime(df["date"])
        df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce")
        df = df.sort_values("date").dropna()

        if len(df) < 13:
            return None

        curr = df.iloc[-1]["revenue"]
        prev_m = df.iloc[-2]["revenue"]
        prev_q = df.iloc[-4]["revenue"]
        prev_y = df.iloc[-13]["revenue"]

        def pct(a, b):
            return (a - b) / b * 100 if b else None

        return {
            "rev": round(curr / 1e8, 2),
            "mom": round(pct(curr, prev_m), 2),
            "qoq": round(pct(curr, prev_q), 2),
            "yoy": round(pct(curr, prev_y), 2),
        }

    except Exception as e:
        print(f"❌ revenue error {stock_id}: {e}")
        return None


def build_static_row(s: dict) -> dict:
    stock_id = str(s["stock_id"])
    name = s["name"]

    row = {
        "stock_id": stock_id,
        "name": name,

        "eps_Y": None,
        "eps_ttm": None,
        "per_Y": None,
        "per_ttm": None,

        "rev": None,
        "rev_mom": None,
        "rev_qoq": None,
        "rev_yoy": None,

        "gross_margin": None,
        "gross_margin_qoq": None,
        "gross_margin_yoy_diff": None,

        "operating_margin": None,
        "operating_margin_qoq": None,
        "operating_margin_yoy_diff": None,

        "net_margin": None,
        "net_margin_qoq": None,
        "net_margin_yoy_diff": None,

        "per_latest": None,
        "per_90d_high": None,
        "per_90d_low": None,
        "pbr_latest": None,
        "pbr_90d_high": None,
        "pbr_90d_low": None,

        "static_updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "static_status": "ok",
        "static_reason": "",
    }

    try:
        eps_res = get_eps_analysis(stock_id, 1)
        print("EPS test =", stock_id, get_eps_analysis(stock_id, 1))
        eps_res = tuple(eps_res) if isinstance(eps_res, tuple) else (None,) * 4
        eps_res = eps_res + (None,) * (4 - len(eps_res))
        eps_last, eps_ttm, per_last, per_ttm = eps_res

        row["eps_Y"] = eps_last
        row["eps_ttm"] = eps_ttm
        row["per_Y"] = per_last
        row["per_ttm"] = per_ttm

        rev = get_revenue_trend(stock_id) or {}
        row["rev"] = rev.get("rev")
        row["rev_mom"] = rev.get("mom")
        row["rev_qoq"] = rev.get("qoq")
        row["rev_yoy"] = rev.get("yoy")

        profit_res = get_profit_ratio(stock_id)
        cur_g, qoq_g, yoy_g = extract_metric(profit_res, "gross")
        cur_o, qoq_o, yoy_o = extract_metric(profit_res, "op")
        cur_n, qoq_n, yoy_n = extract_metric(profit_res, "net")

        row["gross_margin"] = cur_g
        row["gross_margin_qoq"] = qoq_g
        row["gross_margin_yoy_diff"] = yoy_g

        row["operating_margin"] = cur_o
        row["operating_margin_qoq"] = qoq_o
        row["operating_margin_yoy_diff"] = yoy_o

        row["net_margin"] = cur_n
        row["net_margin_qoq"] = qoq_n
        row["net_margin_yoy_diff"] = yoy_n

        per_pbr = get_per_pbr_90d_stats(stock_id) or {}
        row["per_latest"] = per_pbr.get("per")
        row["per_90d_high"] = per_pbr.get("per_90d_high")
        row["per_90d_low"] = per_pbr.get("per_90d_low")
        row["pbr_latest"] = per_pbr.get("pbr")
        row["pbr_90d_high"] = per_pbr.get("pbr_90d_high")
        row["pbr_90d_low"] = per_pbr.get("pbr_90d_low")

    except RuntimeError as e:
        row["static_status"] = "runtime_error"
        row["static_reason"] = str(e)
        raise
    except Exception as e:
        row["static_status"] = "error"
        row["static_reason"] = str(e)
        print(f"❌ static error {stock_id} {name}: {e}")

    return row


def build_all_static(stock_list: list[dict]) -> pd.DataFrame:
    rows = []
    total = len(stock_list)

    for i, s in enumerate(stock_list, 1):
        print(f"處理靜態資料 {i}/{total}: {s['stock_id']} {s['name']}")
        row = build_static_row(s)
        rows.append(row)

    df = pd.DataFrame(rows)

    ordered_cols = [
        "stock_id", "name",
        "eps_Y", "eps_ttm", "per_Y", "per_ttm",
        "rev", "rev_mom", "rev_qoq", "rev_yoy",
        "gross_margin", "gross_margin_qoq", "gross_margin_yoy_diff",
        "operating_margin", "operating_margin_qoq", "operating_margin_yoy_diff",
        "net_margin", "net_margin_qoq", "net_margin_yoy_diff",
        "per_latest", "per_90d_high", "per_90d_low",
        "pbr_latest", "pbr_90d_high", "pbr_90d_low",
        "static_updated_at", "static_status", "static_reason",
    ]
    existing_cols = [c for c in ordered_cols if c in df.columns]
    return df[existing_cols]


def main():
    try:
        csv_file = config.CSV_FILE
        static_output_file = getattr(
            config, "STATIC_OUTPUT_FILE", "AllStatic.csv")

        src_df = pd.read_csv(csv_file, sep="\t",
                             encoding="utf-8-sig", dtype=str)
        src_df.columns = src_df.columns.str.strip()

        stock_list = src_df.rename(
            columns={"Ticker": "stock_id", "Name": "name"}
        ).to_dict(orient="records")

    except Exception as e:
        print(f"❌ 讀取 config.yml 或 CSV 失敗: {e}")
        return

    start_used = start_limit = start_remain = None

    try:
        print("📊 執行前查詢 FinMind 使用量...")
        start_used, start_limit, start_remain = get_finmind_usage()

        estimated_calls = len(stock_list) * 4
        if start_remain < estimated_calls:
            print(
                f"⚠️ FinMind 剩餘額度可能不足，remain={start_remain}, estimated={estimated_calls}，仍繼續執行"
            )

        print(f"🚀 開始產生靜態資料: {static_output_file}")
        static_df = build_all_static(stock_list)

        try:
            static_df.to_csv(static_output_file, index=False,
                             encoding="utf-8-sig")
            print(f"✅ AllStatic 已生成：{static_output_file}")
            print(f"筆數: {len(static_df)}")
        except Exception as e:
            print(f"❌ AllStatic.csv 寫入失敗: {e}")

    finally:
        try:
            print("📊 執行後查詢 FinMind 使用量...")
            end_used, end_limit, end_remain = get_finmind_usage()
            if start_used is not None and end_used is not None:
                print(
                    f"📉 本次約使用 {end_used - start_used} 次 API，剩餘 {end_remain}/{end_limit}"
                )
        except Exception as e:
            print(f"⚠️ 無法查詢執行後 FinMind 使用量: {e}")


if __name__ == "__main__":
    main()
