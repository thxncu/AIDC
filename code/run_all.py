"""Main analyses on the KPX 2023-2025 data and the GPU Monte Carlo.

Usage:  python run_all.py <kpx_raw_dir> <results_dir>

Sections
  1  Data QC
  2  Availability 2023-2025 with two denominators (interpolated year-end and Plan p.50 summer)
  3  Intraday minimum reserve margin, 2030 (Supplementary Table S5)
  4  Back-cast of the availability rule against observed 2023-2025 peaks
  5  Headroom under the Plan's own reserve-margin decomposition (Table 4, Fig. 2a); KPX emergency stages
  6  Peak-event duration (for DC flexibility)
  7  Availability vs. demand level (endogeneity check, Supplementary Section S2.1)
  8  Monte Carlo GPU increment (Table 2 specification, Fig. 1a): independent and correlated inputs
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402
from data import load_kpx  # noqa: E402

RAW, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
log = {}


def save(df, name):
    df.to_csv(os.path.join(OUT, name), index=False, encoding="utf-8-sig")


# ------------------------------------------------------------------ 1. QC
g, qc = load_kpx(RAW)
log["qc"] = qc
YEARS = sorted(g["year"].unique())


def daily_peaks(gy):
    """One row per day: max demand and supply at the moment of max demand."""
    i = gy.groupby("date")["demand"].idxmax()
    d = gy.loc[i, ["date", "datetime", "demand", "supply", "sup_res"]].reset_index(drop=True)
    return d


# ------------------------------------------ 2. Availability by denominator
def availability_table(denoms, label):
    rows = []
    for y in YEARS:
        E = denoms.get(y)
        gy = g[g["year"] == y]
        dmax = gy.groupby("date")["demand"].max()
        top_days = dmax.nlargest(20).index
        top = gy[gy["date"].isin(top_days)]["supply"]
        summer = gy[gy["month"].isin([7, 8])]["supply"]
        row = {"year": y, "denominator": label,
               "effcap_GW": E if E is None else E}
        if E is None:
            row.update({k: np.nan for k in ["top20_mean", "top20_p5", "summer_mean", "summer_p5"]})
        else:
            Emw = E * 1000
            row.update({
                "top20_mean": 100 * (top / Emw).mean(),
                "top20_p5": 100 * (top / Emw).quantile(0.05),
                "summer_mean": 100 * (summer / Emw).mean(),
                "summer_p5": 100 * (summer / Emw).quantile(0.05),
            })
        rows.append(row)
    return pd.DataFrame(rows)


av_interp = availability_table(C.INTERP_EFFCAP_GW, "interpolated year-end denominators (120.7/123.8/126.9)")
av_plan = availability_table({2024: C.PLAN_SUMMER_EFFCAP_GW[2024], 2025: C.PLAN_SUMMER_EFFCAP_GW[2025]},
                             "Plan p.50 summer effective capacity")
av_tab = pd.concat([av_interp, av_plan], ignore_index=True)
save(av_tab.round(3), "availability_2023_2025_by_denominator.csv")

# ------------------- 3. Intraday minimum reserve margin (Supplementary Table S5)
day = g[g["date"] == pd.to_datetime(C.INTRADAY_PROFILE_DAY).date()].reset_index(drop=True)
d_day = day["demand"].values
s_day = day["supply"].values
avail_norm = s_day / s_day[d_day.argmax()]          # supply pattern, =1 at peak-demand instant


def intraday_min(effcap_mw, av, excess_mw, target_mw):
    dem2030 = d_day * target_mw / d_day.max()
    sup = effcap_mw * av * avail_norm
    rm = 100 * (sup - (dem2030 + excess_mw)) / (dem2030 + excess_mw)
    k = rm.argmin()
    return rm[k], day.loc[k, "datetime"].strftime("%H:%M"), avail_norm[k], dem2030[k] / dem2030.max()


# KPX demand and the availability ratio are market-basis, so the scope-consistent table scales demand to
# the Plan's market-basis target (105.2 GW, p.31). The system-basis target (111,383 MW, p.30) mixes a
# market-basis ratio with system-basis demand; it is kept for 90 % and 83 % to show that effect.
rows = []
cases = [(C.PLAN_SUMMER_EFFCAP_GW[2030], "summer 135.6 (Plan p.50)", "market 105.2 (Plan p.31)",
          C.TARGET_DEMAND_2030_MARKET_MW, C.AVAILABILITY_SCENARIOS),
         (C.PLAN_YEAREND_EFFCAP_2030_GW, "year-end 136.7 (Plan p.51)", "system 111.4 (Plan p.30)",
          C.TARGET_DEMAND_2030_MW, [0.90, 0.83]),
         (C.PLAN_SUMMER_EFFCAP_GW[2030], "summer 135.6 (Plan p.50)", "system 111.4 (Plan p.30)",
          C.TARGET_DEMAND_2030_MW, [0.90, 0.83])]
for effcap, lab, dlab, dmw, avs in cases:
    for av in avs:
        for x in C.DC_EXCESS_GW:
            m, t, a_n, d_n = intraday_min(effcap * 1000, av, x * 1000, dmw)
            simple = 100 * (effcap * av - (dmw / 1000 + x)) / (dmw / 1000 + x)
            rows.append({"effcap": lab, "target_demand": dlab, "availability": av, "dc_excess_GW": x,
                         "intraday_min_RM_pct": m, "time_of_min": t,
                         "supply_pattern_at_min": a_n, "demand_rel_to_peak_at_min": d_n,
                         "simple_ratio_RM_pct": simple})
intraday = pd.DataFrame(rows)
save(intraday.round(3), "intraday_reserve_table.csv")
log["intraday_reserve_time_of_min_83pct"] = intraday[(intraday.target_demand.str.startswith("market"))
                                                     & (intraday.availability == 0.83)][
    ["dc_excess_GW", "time_of_min", "supply_pattern_at_min", "demand_rel_to_peak_at_min"]].round(3).to_dict("records")

# ---------------------------------------------------------- 4. Back-cast
rows = []
for y in YEARS:
    gy = g[g["year"] == y]
    k = gy["demand"].idxmax()
    pk = gy.loc[k]
    D, S = pk["demand"] / 1000, pk["supply"] / 1000
    actual = 100 * (S - D) / D
    for lab, E in [("interpolated year-end", C.INTERP_EFFCAP_GW.get(y)),
                   ("Plan p.50 summer", C.PLAN_SUMMER_EFFCAP_GW.get(y))]:
        if E is None:
            continue
        row = {"year": y, "peak_time": str(pk["datetime"]), "peak_demand_GW": D,
               "supply_GW": S, "actual_reserve_GW": S - D, "actual_RM_pct": actual,
               "denominator": lab, "effcap_GW": E, "availability_at_peak_pct": 100 * S / E,
               "expost_RM_at_83pct": 100 * (0.83 * E - D) / D}
        row["expost_error_pp"] = row["expost_RM_at_83pct"] - actual
        if y in C.PLAN_MARKET_TARGET_DEMAND_GW:        # market basis, the scope of KPX demand
            Dp = C.PLAN_MARKET_TARGET_DEMAND_GW[y]
            row.update({"plan_market_target_GW": Dp, "plan_market_minus_actual_GW": Dp - D,
                        "exante_RM_at_83pct": 100 * (0.83 * E - Dp) / Dp})
            row["exante_error_pp"] = row["exante_RM_at_83pct"] - actual
        rows.append(row)
bc = pd.DataFrame(rows)
save(bc.round(3), "backcast_annual_peak.csv")

# top-20 day version (daily peak instants), Plan-independent availability check
rows = []
for y in YEARS:
    dp = daily_peaks(g[g["year"] == y]).nlargest(20, "demand")
    for lab, E in [("interpolated year-end", C.INTERP_EFFCAP_GW.get(y)),
                   ("Plan p.50 summer", C.PLAN_SUMMER_EFFCAP_GW.get(y))]:
        if E is None:
            continue
        act = 100 * (dp.supply - dp.demand) / dp.demand
        pred = 100 * (0.83 * E * 1000 - dp.demand) / dp.demand
        rows.append({"year": y, "denominator": lab, "days": len(dp),
                     "actual_RM_mean": act.mean(), "actual_RM_min": act.min(),
                     "pred_RM_mean_83pct": pred.mean(), "mean_error_pp": (pred - act).mean(),
                     "availability_mean_pct": (100 * dp.supply / (E * 1000)).mean()})
save(pd.DataFrame(rows).round(3), "backcast_top20_days.csv")

# ---------------------------------------------------------- 5. Headroom
S30, D30 = C.PLAN_SUMMER_EFFCAP_GW[2030], C.PLAN_TARGET_DEMAND_GW[2030]
rm = C.PLAN_RM_2030
thr = [("Plan 2030 as planned", 100 * (S30 / D30 - 1)),
       ("Applied medium-term standard", rm["applied_medium_term"]),
       ("Computed 2030 standard (13.1+6.1+0.9)", rm["computed_total"]),
       ("Demand-uncertainty buffer exhausted (13.1+0.9)", rm["capacity_adequacy_LOLE"] + rm["supply_uncertainty"]),
       ("LOLE 0.3 day/yr level (13.1)", rm["capacity_adequacy_LOLE"])]
hr = pd.DataFrame([{"threshold": n, "installed_RM_pct": v,
                    "dc_headroom_GW": S30 / (1 + v / 100) - D30} for n, v in thr])
save(hr.round(2), "headroom_plan_decomposition.csv")
scen = pd.DataFrame([{"dc_excess_GW": x, "installed_RM_pct": 100 * (S30 / (D30 + x) - 1)}
                     for x in C.DC_EXCESS_GW])
save(scen.round(2), "headroom_scenarios.csv")

# operational lens vs KPX emergency stages, at the Plan's market-basis 2030 target (scope of KPX data)
D30m = C.PLAN_MARKET_TARGET_DEMAND_GW[2030]
rows = []
for av_lab, av in [("83% rule", 0.83),
                   ("2025 top-20 mean, summer denominator",
                    av_plan.loc[av_plan.year == 2025, "top20_mean"].values[0] / 100),
                   ("2024 top-20 mean, summer denominator",
                    av_plan.loc[av_plan.year == 2024, "top20_mean"].values[0] / 100)]:
    avail = S30 * av
    r = {"availability": av_lab, "availability_pct": 100 * av, "available_GW": avail,
         "reserve_at_plan_market_demand_GW": avail - D30m}
    for st, gw in C.KPX_EMERGENCY_STAGES_GW.items():
        r[f"headroom_to_{st.split()[0]}_GW"] = avail - D30m - gw
    rows.append(r)
save(pd.DataFrame(rows).round(3), "operational_lens_emergency_stages.csv")

# ------------------------------------------------------ 6. Peak duration


def longest_run_hours(mask):
    if not mask.any():
        return 0.0
    m = np.r_[False, mask, False].astype(int)
    d = np.diff(m)
    starts, ends = np.where(d == 1)[0], np.where(d == -1)[0]
    return (ends - starts).max() / 12


rows = []
for y in YEARS:
    gy = g[g["year"] == y]
    top_days = gy.groupby("date")["demand"].max().nlargest(20).index
    for dte in top_days:
        s = gy[gy["date"] == dte].sort_values("datetime")
        dm = s["demand"].values
        rows.append({"year": y, "date": str(dte), "daily_peak_GW": dm.max() / 1000,
                     "peak_time": s.loc[s["demand"].idxmax(), "datetime"].strftime("%H:%M"),
                     "hours_ge_97pct_daily_peak": longest_run_hours(dm >= 0.97 * dm.max()),
                     "hours_ge_95pct_daily_peak": longest_run_hours(dm >= 0.95 * dm.max()),
                     "hours_ge_90pct_daily_peak": longest_run_hours(dm >= 0.90 * dm.max())})
pdur = pd.DataFrame(rows)
save(pdur.round(2), "peak_duration_top20_days.csv")
summ = pdur.groupby("year")[["hours_ge_97pct_daily_peak", "hours_ge_95pct_daily_peak",
                             "hours_ge_90pct_daily_peak"]].agg(["median", "max"]).round(2)
log["peak_duration_median_max_hours"] = {
    str(y): {c: [float(summ.loc[y, (c, "median")]), float(summ.loc[y, (c, "max")])]
             for c in ["hours_ge_97pct_daily_peak", "hours_ge_95pct_daily_peak", "hours_ge_90pct_daily_peak"]}
    for y in summ.index}
for h in [3, 4, 6]:
    log[f"share_top20_days_97pct_window_le_{h}h"] = round(float((pdur.hours_ge_97pct_daily_peak <= h).mean()), 3)
    log[f"share_top20_days_95pct_window_le_{h}h"] = round(float((pdur.hours_ge_95pct_daily_peak <= h).mean()), 3)

# multi-day heat events: consecutive days with daily peak >= 95% of annual peak
rows = []
for y in YEARS:
    dmax = g[g["year"] == y].groupby("date")["demand"].max()
    hot = dmax[dmax >= 0.95 * dmax.max()].index
    dts = pd.to_datetime(pd.Series(sorted(hot)))
    runs = (dts.diff() != pd.Timedelta("1D")).cumsum()
    lens = dts.groupby(runs).size()
    rows.append({"year": y, "days_ge_95pct_annual_peak": len(hot),
                 "longest_consecutive_days": int(lens.max()), "events": int(len(lens))})
save(pd.DataFrame(rows), "peak_multiday_events.csv")

# ------------------------------------------- 7. Availability vs demand
rows = []
for y in YEARS:
    dp = daily_peaks(g[(g["year"] == y) & g["month"].isin([6, 7, 8, 9])])
    E = C.INTERP_EFFCAP_GW[y] * 1000
    dp["year"] = y
    dp["avail"] = 100 * dp["supply"] / E
    dp["load_ratio"] = 100 * dp["demand"] / E
    rows.append(dp)
av = pd.concat(rows, ignore_index=True)
Xd = pd.get_dummies(av["year"], prefix="y", dtype=float)
Xm = np.column_stack([av["load_ratio"].values, Xd.values])
beta, *_ = np.linalg.lstsq(Xm, av["avail"].values, rcond=None)
resid = av["avail"].values - Xm @ beta
ss_res = (resid ** 2).sum()
# within-year R-squared
within = av["avail"] - av.groupby("year")["avail"].transform("mean")
r2_within = 1 - ss_res / (within ** 2).sum()
n, k = Xm.shape
se = np.sqrt(ss_res / (n - k) * np.linalg.inv(Xm.T @ Xm)[0, 0])
log["availability_vs_load"] = {"slope_pp_avail_per_pp_load": round(float(beta[0]), 3),
                               "se": round(float(se), 3), "r2_within": round(float(r2_within), 3),
                               "n_days": int(n), "months": "Jun-Sep", "denominator": "interpolated year-end"}
av["load_decile"] = av.groupby("year")["load_ratio"].transform(lambda s: pd.qcut(s, 5, labels=False) + 1)
save(av.groupby(["year", "load_decile"])[["load_ratio", "avail"]].mean().reset_index().round(2),
     "availability_by_load_quintile.csv")

# --------------------------------------------------------- 8. Monte Carlo
rng = np.random.default_rng(C.MC_SEED)
N = C.MC_N


def draw(u):
    """Map uniforms (N x 4) to P_max, OH, U (peak utilization factor), PUE as specified in Table 2."""
    # GPU power bounds: maximum TGP of Hopper (700 W) and Blackwell Ultra (1,400 W),
    # NVIDIA Technical Blog, Aubrey & Stam (22 Aug 2025), Table 2; mode at the midpoint.
    P = stats.triang.ppf(u[:, 0], c=(1050 - 700) / (1400 - 700), loc=700, scale=700)
    OH = stats.lognorm.ppf(u[:, 1], s=0.15, scale=np.exp(0.43))
    # peak utilization factor U: assumed share of maximum power drawn at the system peak; range informed by
    # the operating-time assumptions of Shehabi et al. (2024), not estimated from them
    U = 0.40 + 0.45 * stats.beta.ppf(u[:, 2], 3, 3)
    a, b = (1.2 - 1.4) / 0.1, (1.6 - 1.4) / 0.1
    PUE = stats.truncnorm.ppf(u[:, 3], a, b, loc=1.4, scale=0.1)
    return P, OH, U, PUE


def gpu_mw(P, OH, U, PUE, realization=1.0):
    return C.N_GPU * P * OH * U * PUE * realization / 1e6


NETWORK_FACTOR = 1.14
variants = {"independent": np.eye(4)}
R = np.eye(4)
R[0, 3] = R[3, 0] = -0.4   # higher-power GPUs -> liquid cooling -> lower PUE
R[2, 3] = R[3, 2] = -0.3   # higher peak utilization factor -> lower PUE (fixed overhead spread)
variants["correlated (rho_P,PUE=-0.4; rho_U,PUE=-0.3)"] = R
rows = []
for name, Rm in variants.items():
    z = rng.multivariate_normal(np.zeros(4), Rm, size=N)
    u = stats.norm.cdf(z)
    P, OH, U, PUE = draw(u)
    for real in [1.0, 0.75, 0.5]:
        mw = gpu_mw(P, OH, U, PUE, real)
        if name == "independent" and real == 1.0:
            save(pd.DataFrame({"gpu_MW": mw}).round(3), "monte_carlo_draws_independent.csv")
        rows.append({"variant": name, "realization": real, "median_MW": np.median(mw),
                     "p5_MW": np.percentile(mw, 5), "p95_MW": np.percentile(mw, 95),
                     "mean_MW": mw.mean()})
    if name == "independent":
        # IT equipment outside the servers, mainly networking: about 14 % of server power at peak
        # operation (Epoch AI, 2025); Eq. (2) excludes it, so it is reported as a variant.
        mw = gpu_mw(P, OH, U, PUE) * NETWORK_FACTOR
        rows.append({"variant": "independent, with networking (x1.14)", "realization": 1.0,
                     "median_MW": np.median(mw), "p5_MW": np.percentile(mw, 5),
                     "p95_MW": np.percentile(mw, 95), "mean_MW": mw.mean()})
mc = pd.DataFrame(rows)
save(mc.round({"median_MW": 1, "p5_MW": 1, "p95_MW": 1, "mean_MW": 1}), "monte_carlo_gpu_increment.csv")

# tornado (one-at-a-time P5/P95, others at median), Eq. (2) only
med = draw(np.full((1, 4), 0.5))
names = ["GPU power", "Server overhead", "Peak utilization factor", "PUE"]
rows = []
for i, nm in enumerate(names):
    vals = []
    for q in [0.05, 0.95]:
        u = np.full((1, 4), 0.5)
        u[0, i] = q
        vals.append(gpu_mw(*draw(u))[0])
    rows.append({"parameter": nm, "low_MW": vals[0], "high_MW": vals[1], "swing_MW": vals[1] - vals[0]})
save(pd.DataFrame(rows).sort_values("swing_MW", ascending=False).round(1), "monte_carlo_tornado.csv")
log["mc_median_point_MW"] = round(float(gpu_mw(*med)[0]), 1)

with open(os.path.join(OUT, "run_log.json"), "w", encoding="utf-8") as f:
    json.dump(log, f, ensure_ascii=False, indent=2, default=str)
print(json.dumps(log, ensure_ascii=False, indent=2, default=str))
