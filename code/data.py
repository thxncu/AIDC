"""Load and clean KPX 5-minute national supply-demand data.

Source: KPX, "5분단위 전국 전력수급현황" (data.go.kr dataset 15099819),
downloaded from https://openapi.kpx.or.kr/sukub.do in 3-month files.
Each CSV (EUC-KR) has 8 columns:
기준일시, 공급능력(MW), 현재수요(MW), 최대예측수요(MW), 공급예비력(MW),
공급예비율(%), 운영예비력(MW), 운영예비율(%)
"""
import glob
import os

import numpy as np
import pandas as pd

COLS = ["datetime", "supply", "demand", "max_fcst",
        "sup_res", "sup_res_rate", "op_res", "op_res_rate"]


def load_kpx(raw_dir: str) -> tuple[pd.DataFrame, dict]:
    files = sorted(glob.glob(os.path.join(raw_dir, "**", "*.csv"), recursive=True))
    if not files:
        raise FileNotFoundError(f"No CSV files under {raw_dir}")
    frames = []
    for f in files:
        df = pd.read_csv(f, encoding="euc-kr")
        if df.shape[1] != len(COLS):
            raise ValueError(f"{f}: expected {len(COLS)} columns, got {df.shape[1]}")
        df.columns = COLS
        df["datetime"] = pd.to_datetime(df["datetime"].astype(str), format="%Y%m%d%H%M%S")
        frames.append(df)
    g = pd.concat(frames, ignore_index=True).sort_values("datetime")
    n_raw = len(g)
    n_dup = int(g["datetime"].duplicated().sum())
    g = g.drop_duplicates("datetime")
    bad = g["supply"] <= 0
    n_bad = int(bad.sum())
    g = g[~bad].reset_index(drop=True)

    full = pd.date_range(g["datetime"].min(), g["datetime"].max(), freq="5min")
    missing = full.difference(g["datetime"])
    longest = 0
    if len(missing):
        s = pd.Series(missing)
        runs = (s.diff() != pd.Timedelta("5min")).cumsum()
        longest = int(s.groupby(runs).size().max())

    # KPX supply reserve is computed against demand + delta. Before Jul 2024
    # delta was 0-1.5 GW (largest at night); from Jul 2024 it is zero.
    delta = (g["supply"] - g["sup_res"]) - g["demand"]

    g["date"] = g["datetime"].dt.date
    g["year"] = g["datetime"].dt.year
    g["month"] = g["datetime"].dt.month
    g["hour"] = g["datetime"].dt.hour + g["datetime"].dt.minute / 60

    qc = {
        "files": len(files),
        "rows_raw": n_raw,
        "duplicates_dropped": n_dup,
        "nonpositive_supply_dropped": n_bad,
        "rows_clean": len(g),
        "expected_5min_intervals": len(full),
        "missing_intervals": len(missing),
        "missing_share_pct": round(100 * len(missing) / len(full), 3),
        "longest_gap_intervals": longest,
        "first": str(g["datetime"].min()),
        "last": str(g["datetime"].max()),
        "reserve_delta_mean_MW_2023": round(float(delta[g["year"] == 2023].mean()), 1),
        "reserve_delta_mean_MW_2025": round(float(delta[g["year"] == 2025].mean()), 1),
        "reserve_delta_at_16_18h_summer_2023_MW": round(float(
            delta[(g["year"] == 2023) & g["month"].isin([7, 8]) & g["hour"].between(16, 18)].mean()), 1),
    }
    return g, qc
