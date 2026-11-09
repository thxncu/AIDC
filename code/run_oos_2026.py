"""Back-cast on summers 2023-2026 (June-September), with summer 2026 held out as an out-of-sample check.

Usage:  python run_oos_2026.py <kpx_raw_dir 2023-2025> <kpx_2026_dir> <results_dir>

Questions asked of the 2026 data, each with the rule fixed on 2023-2025 data:
  1  Back-cast of the reserve at the summer peak hour: constant 83 % availability rule, ex post (actual
     demand) and ex ante (Plan target demand), and a load-conditional availability fitted on 2024-2025
     (Table 5). Hourly averages, the resolution of the Plan's targets and of KPX's published peak
     statistics. KPX demand and supply capacity are market-basis, so the ex ante test uses the Plan's
     market-basis targets (p.31). The availability ratio divides KPX (market) supply capacity by the
     Plan's (system) effective capacity, so 0.83 x effective capacity estimates market supply capacity
     and is compared with market demand. The ex ante value with the system-basis targets (p.30) is
     kept as a separate column to show the effect of mixing the two bases.
  2  Same for the 20 highest-demand summer days (hourly daily peaks).
  3  Timing of daily peaks (has the peak moved later in the day?).
  4  Length of peak windows on the top-20 days (input to the flexibility analysis).
  5  Lowest supply reserve of the summer and time below the KPX emergency stages.
  6  Availability table for 2023-2026 on the same definitions (Supplementary Table S4).
Top-20 days are taken within June-September in every year, because 2026 covers only those months.
Denominator: the Plan's summer effective capacity (p.50) of the same year.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402
from data import load_kpx  # noqa: E402

RAW, RAW26, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
AV = 0.83
FIT_YEARS = [2024, 2025]          # years with a Plan p.50 summer value; 2023 has none
YEARS = [2023, 2024, 2025, 2026]

g0, _ = load_kpx(RAW)
g1, qc26 = load_kpx(RAW26)
assert g1["datetime"].dt.year.unique().tolist() == [2026]
g = pd.concat([g0, g1], ignore_index=True)
g = g[g["month"].isin([6, 7, 8, 9])].reset_index(drop=True)
log = {"qc_2026": {k: v for k, v in qc26.items() if not k.startswith("reserve_delta")}}


def save(df, name):
    df.to_csv(os.path.join(OUT, name), index=False, encoding="utf-8-sig")


def daily_peaks(gy):
    i = gy.groupby("date")["demand"].idxmax()
    return gy.loc[i, ["date", "datetime", "demand", "supply", "sup_res"]].reset_index(drop=True)


# hourly averages (interval ending at :05 ... :00 belongs to the hour that starts at the previous :00)
g["hour"] = (g["datetime"] - pd.Timedelta("5min")).dt.floor("h")
hr = g.groupby("hour").agg(demand=("demand", "mean"), supply=("supply", "mean"),
                           n=("demand", "size")).reset_index()
hr = hr[(hr["n"] >= 9) & hr["hour"].dt.month.isin([6, 7, 8, 9])].reset_index(drop=True)
hr["year"], hr["date"] = hr["hour"].dt.year, hr["hour"].dt.date
log["hourly_basis"] = {"min_intervals_per_hour": 9, "hours": int(len(hr))}


def daily_peaks_h(hy):
    i = hy.groupby("date")["demand"].idxmax()
    return hy.loc[i, ["date", "hour", "demand", "supply"]].reset_index(drop=True)


# -------------------------------------------- load-conditional availability (fit on 2024-2025)
# five-minute daily peaks (peak timing, section 3) and hourly daily peaks (fit and back-cast)
dp_all = []
for y in YEARS:
    dp = daily_peaks(g[g["year"] == y])
    dp["year"] = y
    dp_all.append(dp)
dp_all = pd.concat(dp_all, ignore_index=True)
dph_all = []
for y in YEARS:
    dp = daily_peaks_h(hr[hr["year"] == y])
    dp["year"] = y
    E = C.PLAN_SUMMER_EFFCAP_GW.get(y)
    dp["E_GW"] = E
    if E is not None:
        dp["avail_pct"] = 100 * dp["supply"] / (E * 1000)
        dp["load_ratio_pct"] = 100 * dp["demand"] / (E * 1000)
    dph_all.append(dp)
dph_all = pd.concat(dph_all, ignore_index=True)
fit = dph_all[dph_all["year"].isin(FIT_YEARS)]
b, a = np.polyfit(fit["load_ratio_pct"], fit["avail_pct"], 1)
log["load_conditional_fit"] = {"years": FIT_YEARS, "n_days": int(len(fit)), "intercept": round(float(a), 3),
                               "slope": round(float(b), 3), "denominator": "Plan p.50 summer",
                               "resolution": "hourly daily peaks"}


def avail_hat(load_ratio_pct):
    return (a + b * load_ratio_pct) / 100


# ------------------------------------------------------------------ 1. summer peak hour
rows = []
for y in YEARS:
    hy = hr[hr["year"] == y]
    pk = hy.loc[hy["demand"].idxmax()]
    D, S = pk["demand"] / 1000, pk["supply"] / 1000
    E = C.PLAN_SUMMER_EFFCAP_GW.get(y, C.INTERP_EFFCAP_GW.get(y))
    r = {"year": y, "sample": "out-of-sample" if y == 2026 else "in-sample",
         "peak_hour_start": str(pk["hour"]), "peak_demand_GW": D, "supply_GW": S,
         "actual_reserve_GW": S - D, "actual_RM_pct": 100 * (S - D) / D,
         "kpx_published_peak_GW": C.KPX_PUBLISHED_SUMMER_PEAK_MW.get(y, np.nan) / 1000,
         "kpx_total_demand_estimate_GW": C.KPX_TOTAL_DEMAND_ESTIMATE_AT_PEAK_MW.get(y, np.nan) / 1000,
         "effcap_GW": E, "denominator": "Plan p.50 summer" if y in C.PLAN_SUMMER_EFFCAP_GW
         else "interpolated year-end (no Plan value)",
         "availability_at_peak_pct": 100 * S / E, "expost_RM_83pct": 100 * (AV * E - D) / D}
    r["expost_error_pp_83pct"] = r["expost_RM_83pct"] - r["actual_RM_pct"]
    if y in C.PLAN_MARKET_TARGET_DEMAND_GW:
        Dm, Ds = C.PLAN_MARKET_TARGET_DEMAND_GW[y], C.PLAN_TARGET_DEMAND_GW[y]
        ah = avail_hat(100 * D / E)
        r.update({"plan_market_target_GW": Dm, "plan_market_minus_actual_GW": Dm - D,
                  "plan_system_target_GW": Ds, "plan_system_minus_market_GW": Ds - Dm,
                  "exante_RM_83pct_market": 100 * (AV * E - Dm) / Dm,
                  "exante_RM_83pct_system_mixed": 100 * (AV * E - Ds) / Ds,
                  "load_cond_availability_pct": 100 * ah,
                  "expost_RM_load_cond": 100 * (ah * E - D) / D})
        for k in ["exante_RM_83pct_market", "exante_RM_83pct_system_mixed", "expost_RM_load_cond"]:
            r[k.replace("RM", "error_pp")] = r[k] - r["actual_RM_pct"]
        r["shortfall_vs_load_cond_GW"] = (ah * E) - S
    rows.append(r)
peak = pd.DataFrame(rows)
save(peak.round(3), "oos_2026_summer_peak_backcast.csv")

# ------------------------------------------------------------------ 2. top-20 summer days
rows = []
for y in YEARS:
    dp = dph_all[dph_all["year"] == y].nlargest(20, "demand")
    E = C.PLAN_SUMMER_EFFCAP_GW.get(y)
    act = 100 * (dp["supply"] - dp["demand"]) / dp["demand"]
    r = {"year": y, "sample": "out-of-sample" if y == 2026 else "in-sample",
         "mean_daily_peak_GW": dp["demand"].mean() / 1000, "actual_RM_mean": act.mean(), "actual_RM_min": act.min()}
    if E is not None:
        p83 = 100 * (AV * E * 1000 - dp["demand"]) / dp["demand"]
        ah = avail_hat(100 * dp["demand"] / (E * 1000))
        plc = 100 * (ah * E * 1000 - dp["demand"]) / dp["demand"]
        r.update({"availability_mean_pct": dp["avail_pct"].mean(), "load_cond_availability_mean_pct": 100 * ah.mean(),
                  "pred_RM_mean_83pct": p83.mean(), "error_pp_83pct": (p83 - act).mean(),
                  "pred_RM_mean_load_cond": plc.mean(), "error_pp_load_cond": (plc - act).mean(),
                  "mae_pp_83pct": (p83 - act).abs().mean(), "mae_pp_load_cond": (plc - act).abs().mean()})
    rows.append(r)
top = pd.DataFrame(rows)
save(top.round(3), "oos_2026_top20_backcast.csv")

# ------------------------------------------------------------------ 3. peak timing
rows = []
for y in YEARS:
    dp = dp_all[dp_all["year"] == y].nlargest(20, "demand")
    hrs = dp["datetime"].dt.hour + dp["datetime"].dt.minute / 60
    rows.append({"year": y, "median_peak_hour_top20": hrs.median(), "share_top20_peak_at_or_after_17h": (hrs >= 17).mean(),
                 "share_top20_peak_at_or_after_18h": (hrs >= 18).mean(),
                 "summer_peak_time": str(dp.loc[dp["demand"].idxmax(), "datetime"])})
timing = pd.DataFrame(rows)
save(timing.round(3), "oos_peak_timing.csv")


# ------------------------------------------------------------------ 4. peak windows
def longest_run_hours(mask):
    if not mask.any():
        return 0.0
    m = np.r_[False, mask, False].astype(int)
    d = np.diff(m)
    return (np.where(d == -1)[0] - np.where(d == 1)[0]).max() / 12


rows = []
for y in YEARS:
    gy = g[g["year"] == y]
    for dte in gy.groupby("date")["demand"].max().nlargest(20).index:
        dm = gy[gy["date"] == dte].sort_values("datetime")["demand"].values
        rows.append({"year": y, "date": str(dte), "h97": longest_run_hours(dm >= 0.97 * dm.max()),
                     "h95": longest_run_hours(dm >= 0.95 * dm.max())})
dur = pd.DataFrame(rows)
dsum = dur.groupby("year").agg(h97_median=("h97", "median"), h97_max=("h97", "max"),
                               h95_median=("h95", "median"), h95_max=("h95", "max"),
                               share_h97_gt_3h=("h97", lambda s: (s > 3).mean())).reset_index()
save(dsum.round(3), "oos_peak_duration_top20.csv")

# ------------------------------------------------------------------ 5. lowest reserve, emergency stages
rows = []
for y in YEARS:
    gy = g[g["year"] == y]
    k = gy["sup_res"].idxmin()
    r = {"year": y, "min_supply_reserve_GW": gy.loc[k, "sup_res"] / 1000, "time_of_min": str(gy.loc[k, "datetime"]),
         "demand_at_min_GW": gy.loc[k, "demand"] / 1000, "supply_at_min_GW": gy.loc[k, "supply"] / 1000}
    for st, gw in C.KPX_EMERGENCY_STAGES_GW.items():
        r[f"hours_below_{st.split()[0]}"] = (gy["sup_res"] < gw * 1000).sum() / 12
    rows.append(r)
low = pd.DataFrame(rows)
save(low.round(3), "oos_min_reserve_emergency_stages.csv")

# ------------------------------------------ 6. availability 2023-2026 (Supplementary Table S4)
# Summer (Jun-Sep) top-20 days and Jul-Aug, Plan p.50 summer denominators. 2023 has no Plan value:
# the interpolated year-end value (120.7 GW) is used and flagged.
rows = []
for y in YEARS:
    E = C.PLAN_SUMMER_EFFCAP_GW.get(y, C.INTERP_EFFCAP_GW.get(y))
    lab = "Plan p.50 summer" if y in C.PLAN_SUMMER_EFFCAP_GW else "interpolated year-end (no Plan value)"
    gy = g[g["year"] == y]
    top_days = gy.groupby("date")["demand"].max().nlargest(20).index
    av_top = gy[gy["date"].isin(top_days)]["supply"] / (E * 1000) * 100
    ja = gy[gy["month"].isin([7, 8])]["supply"] / (E * 1000) * 100
    # market-scope variant: denominator net of generation outside the market, approximated by the Plan's
    # gap between system-basis (p.30) and market-basis (p.31) target demand of the same year
    gap = C.PLAN_TARGET_DEMAND_GW[y] - C.PLAN_MARKET_TARGET_DEMAND_GW[y] if y in C.PLAN_MARKET_TARGET_DEMAND_GW else np.nan
    rows.append({"year": y, "sample": "out-of-sample" if y == 2026 else "in-sample", "denominator": lab,
                 "effcap_GW": E, "top20_mean": av_top.mean(), "top20_p5": av_top.quantile(0.05),
                 "julaug_mean": ja.mean(), "julaug_p5": ja.quantile(0.05),
                 "system_minus_market_target_GW": gap,
                 "top20_mean_net_of_nonmarket": av_top.mean() * E / (E - gap)})
avail = pd.DataFrame(rows)
save(avail.round(3), "availability_2023_2026.csv")
log["availability_2023_2026"] = avail.round(3).to_dict("records")

# Supplementary Section S2.2: 2030 reserve at the Plan's market-basis target demand (the basis of KPX
# demand and of the availability ratio) if the observed 2024-2026 top-20-day availability (Supplementary
# Table S4) is applied to the 2030 summer effective capacity, with and without DC excess, vs KPX
# emergency stages. KPX defines the stages on operating reserve (예비전력); here they are compared with
# supply minus demand, so the comparison is approximate.
S30, D30m = C.PLAN_SUMMER_EFFCAP_GW[2030], C.PLAN_MARKET_TARGET_DEMAND_GW[2030]
rows = []
for _, r in avail[avail["year"].isin([2024, 2025, 2026])].iterrows():
    for x in C.DC_EXCESS_GW:
        res = S30 * r["top20_mean"] / 100 - (D30m + x)
        below = [st for st, gw in C.KPX_EMERGENCY_STAGES_GW.items() if res < gw]
        rows.append({"availability_year": int(r["year"]), "top20_mean_pct": r["top20_mean"],
                     "dc_excess_GW": x, "reserve_2030_GW": res,
                     "deepest_stage_reached": below[-1] if below else "none"})
save(pd.DataFrame(rows).round(3), "oos_2030_reserve_at_observed_availability.csv")

log["summer_peak"] = peak.round(3).to_dict("records")
log["top20"] = top.round(3).to_dict("records")
with open(os.path.join(OUT, "oos_2026_log.json"), "w", encoding="utf-8") as f:
    json.dump(log, f, ensure_ascii=False, indent=2, default=str)
pd.set_option("display.width", 250)
for name, df in [("availability 2023-2026", avail), ("peak", peak), ("top20", top), ("timing", timing), ("duration", dsum), ("low reserve", low)]:
    print(f"\n== {name}\n", df.round(2).to_string(index=False))
print("\nfit", log["load_conditional_fit"])
