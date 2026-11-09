"""RE+ESS self-supply of a 1 GW flat data-centre load, 2024 and 2025.

Usage:  python run_re_ess.py <kpx_raw_dir> <re_dir> <results_dir>

Inputs
  KPX 5-minute national supply-demand (system load and supply reserve, for coincidence metrics)
  KPX "지역별 시간별 태양광 및 풍력 발전량" (data.go.kr 15065269), one CSV per year,
  CP949, columns: 거래일(자), 거래시간 (1-24, hour ending), 지역, 연료원, 전력거래량(MWh)

Solar profile
  The series are traded energy, not physical generation. In most mainland provinces
  they include evening discharge from PV-linked ESS (e.g., 전라남도: 9-10 % of winter
  solar trading occurs after 18:00, i.e., after sunset).
  Base: the mainland region with an after-dark winter share <= 2 % and annual
  trading >= 100 GWh in both years (selected by rule in the code; 부산시 in 2024-2025 data).
  전라남도, 울산시 and 제주도 are sensitivities.
Wind profile: 육지 (mainland). Jeju wind trading collapses after May 2024 (market
  change), so it is used only to calibrate a variability-inflation factor (Jan-May 2024).
Scaling: each profile is divided by its annual maximum hourly output, so
  "S GW of solar" means S GW of peak hourly output, not nameplate capacity.

Chronological dispatch, hourly, load L = 1 GW:
  direct_t    = min(RE_t, L)
  charge_t    = min(P, RE_t - direct_t, (E - SOC_t) / eta_c)
  discharge_t = min(P, L - direct_t, eta_d * SOC_t)
  SOC_{t+1}   = SOC_t + eta_c * charge_t - discharge_t / eta_d
  grid_t      = L - direct_t - discharge_t
  curtail_t   = RE_t - direct_t - charge_t
Base case: eta_c = eta_d = sqrt(0.9), P = 1 GW, warm start (the year is run twice and the
second run starts from the first run's final SOC). Alternative conventions (Supplementary
Table S6): 전라남도 solar, eta_c = 1, eta_d = 0.9 (loss on discharge only), SOC_0 = 0.
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data import load_kpx  # noqa: E402

KPX_DIR, RE_DIR, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)

RE_LEVELS = [(3.0, 1.5), (4.0, 2.0), (5.0, 2.5), (6.0, 3.0)]   # (solar, wind) GW
ESS_LEVELS = [0, 2, 4, 6, 8, 12]                                # GWh
P_ESS = 1.0
LOAD = 1.0
TOP_N = 100
MAIN = [(5.0, 2.5, 8), (6.0, 3.0, 8)]                           # portfolios of Table 6 and Table S6
ALT_SOLAR = "전라남도"         # solar region of the alternative conventions (Table S6)
AFTER_DARK_MAX_PCT = 2.0      # winter (Nov-Jan) share of solar trading in hours ending 19-24
MIN_ANNUAL_GWH = 100.0
METROPOLITAN = {"서울시", "부산시", "대구시", "인천시", "광주시", "대전시", "울산시", "세종시"}


def save(df, name):
    df.to_csv(os.path.join(OUT, name), index=False, encoding="utf-8-sig")


def rnd(df, k=3):
    return df.round({c: k for c in df.columns if pd.api.types.is_float_dtype(df[c])})


# ------------------------------------------------------------------ inputs
def load_re(path):
    df = pd.read_csv(path, encoding="cp949")
    df.columns = ["date", "hour", "region", "fuel", "mwh"]
    df["hour"] = df["hour"].astype(int)
    df["start"] = pd.to_datetime(df["date"]) + pd.to_timedelta(df["hour"] - 1, unit="h")
    df["month"] = df["start"].dt.month
    return df


re_raw = {}
for f in sorted(glob.glob(os.path.join(RE_DIR, "*.csv"))):
    d = load_re(f)
    re_raw[int(d["start"].dt.year.mode()[0])] = d
YEARS = sorted(re_raw)


def series(df, fuel, region):
    s = df[(df["fuel"] == fuel) & (df["region"] == region)].set_index("start")["mwh"].sort_index()
    if s.index.duplicated().any():
        raise ValueError(f"duplicate hours for {fuel}/{region}")
    return s


g, _ = load_kpx(KPX_DIR)
g["start"] = (g["datetime"] - pd.Timedelta("5min")).dt.floor("h")
hourly = g.groupby("start").agg(load=("demand", "mean"), supply=("supply", "mean"))
sys_load = hourly["load"] / 1000                                # GW
sys_reserve = (hourly["supply"] - hourly["load"]) / 1000        # GW

# ------------------------------------------- solar contamination check, region choice
rows = []
for y in YEARS:
    s = re_raw[y][re_raw[y]["fuel"] == "태양광"]
    for reg, x in s.groupby("region"):
        win = x[x["month"].isin([11, 12, 1])]
        summ = x[x["month"].isin([5, 6, 7])]
        rows.append({"year": y, "region": reg, "annual_GWh": x["mwh"].sum() / 1000,
                     "winter_after_18h_pct": 100 * win.loc[win["hour"] >= 19, "mwh"].sum() / win["mwh"].sum(),
                     "summer_after_20h_pct": 100 * summ.loc[summ["hour"] >= 21, "mwh"].sum() / summ["mwh"].sum(),
                     "peak_normalised_CF_pct": 100 * x["mwh"].mean() / x["mwh"].max()})
ad = pd.DataFrame(rows)
save(rnd(ad, 2), "re_solar_after_dark_by_region.csv")
ok = ad.assign(ok=(ad.winter_after_18h_pct <= AFTER_DARK_MAX_PCT) & (ad.annual_GWh >= MIN_ANNUAL_GWH)
               & (ad.region != "제주도")).groupby("region")["ok"].all()
cands = ad[ad.region.isin(ok[ok].index)].groupby("region")["annual_GWh"].mean().sort_values(ascending=False)
if cands.empty:
    raise RuntimeError("no solar region passes the after-dark rule")
BASE_SOLAR = cands.index[0]
SOLAR_ALTS = [ALT_SOLAR, "울산시", "제주도"]

# --------------------------------------------------- wind variability factor
def jeju_wind_name(df):
    return [r for r in df[df["fuel"] == "풍력"]["region"].unique() if r.startswith("제주")][0]


d24 = re_raw[2024]
wm = series(d24, "풍력", "육지")
wj = series(d24, "풍력", jeju_wind_name(d24))
jan_may = (wm.index >= "2024-01-01") & (wm.index < "2024-06-01")
cv = lambda x: np.std(x) / np.mean(x)                             # noqa: E731
cv_main, cv_jeju = cv(wm[jan_may].values), cv(wj[jan_may].values)


def inflate(w, k):
    """Scale deviations from the mean by k, clip to [0, 1], restore the mean."""
    mu = w.mean()
    x = np.clip(mu + k * (w - mu), 0, 1)
    for _ in range(50):
        x = np.clip(x * mu / x.mean(), 0, 1)
    return x


wn = (wm / wm.max()).values
lo, hi = 1.0, 5.0
for _ in range(60):
    k = (lo + hi) / 2
    lo, hi = (k, hi) if cv(inflate(wn, k)[jan_may]) < cv_jeju else (lo, k)
K_WIND = (lo + hi) / 2

# ----------------------------------------------------------------- dispatch


def dispatch(re, E, eta_c, eta_d, soc0):
    n = len(re)
    direct = np.minimum(re, LOAD)
    ch, dis, soc_path = np.zeros(n), np.zeros(n), np.zeros(n)
    soc = soc0
    for t in range(n):
        surplus, deficit = re[t] - direct[t], LOAD - direct[t]
        if E > 0 and surplus > 0:
            c = min(P_ESS, surplus, (E - soc) / eta_c)
            ch[t] = c
            soc += eta_c * c
        if E > 0 and deficit > 0:
            d = min(P_ESS, deficit, eta_d * soc)
            dis[t] = d
            soc -= d / eta_d
        soc_path[t] = soc
    return direct, ch, dis, LOAD - direct - dis, re - direct - ch, soc_path


def run(re, E, convention="base"):
    if convention == "base":
        ec = ed = np.sqrt(0.9)
        soc0 = dispatch(re, E, ec, ed, 0.5 * E)[-1][-1]
    elif convention == "alternative":
        ec, ed, soc0 = 1.0, 0.9, 0.0
    else:
        raise ValueError(convention)
    return dispatch(re, E, ec, ed, soc0), soc0, ec, ed


def metrics(year, S, W, E, re, res, soc0, ec, ed):
    direct, ch, dis, grid, curtail, soc = res
    assert np.allclose(direct + dis + grid, LOAD)
    assert np.allclose(re, direct + ch + curtail)
    assert np.allclose(soc - np.r_[soc0, soc[:-1]], ec * ch - dis / ed)
    assert (grid > -1e-9).all() and (curtail > -1e-9).all()
    idx = pd.date_range(f"{year}-01-01", periods=len(re), freq="h")
    ls, rs = sys_load.reindex(idx), sys_reserve.reindex(idx)
    gs = pd.Series(grid, index=idx)
    top, low = ls.nlargest(TOP_N).index, rs.nsmallest(TOP_N).index
    dec = ls.nlargest(int(round(0.1 * ls.notna().sum()))).index
    on = gs > 0.05
    runs = (on != on.shift()).cumsum()
    run_len = on.groupby(runs).sum()
    starts = on.groupby(runs).apply(lambda s: s.index[0])
    return {
        "year": year, "solar_GW": S, "wind_GW": W, "ess_GWh": E,
        "self_supply_pct": 100 * (direct + dis).sum() / (LOAD * len(re)),
        "grid_GWh": grid.sum(), "curtail_share_pct": 100 * curtail.sum() / re.sum(),
        "grid_max_GW_all_hours": grid.max(),
        f"grid_max_GW_top{TOP_N}_load": gs[top].max(),
        f"share_top{TOP_N}_load_hours_with_grid_pct": 100 * (gs[top] > 0.05).mean(),
        f"grid_max_GW_low{TOP_N}_reserve": gs[low].max(),
        f"share_low{TOP_N}_reserve_hours_with_grid_pct": 100 * (gs[low] > 0.05).mean(),
        "share_grid_energy_in_top10pct_load_hours_pct": 100 * gs[dec].sum() / gs.sum() if gs.sum() > 0 else np.nan,
        "longest_grid_draw_hours": int(run_len.max()),
        "longest_grid_draw_start": str(starts[run_len.idxmax()]),
        "soc_start_end_gap_pct_of_E": 100 * abs(soc[-1] - soc0) / E if E > 0 else 0.0,
    }


def norm(s):
    return (s / s.max()).values


# ----------------------------------------------------------------- profiles
prof, rows = {}, []
for y in YEARS:
    d = re_raw[y]
    w = series(d, "풍력", "육지")
    prof[y] = {"wind": norm(w), "wind_inflated": inflate(norm(w), K_WIND)}
    for reg in [BASE_SOLAR] + SOLAR_ALTS:
        s = series(d, "태양광", reg)
        if len(s) != len(w):
            raise ValueError("solar and wind lengths differ")
        prof[y][f"solar:{reg}"] = norm(s)
    for nm, ser in [(f"solar {BASE_SOLAR} (base)", series(d, "태양광", BASE_SOLAR)),
                    (f"solar {ALT_SOLAR} (sensitivity)", series(d, "태양광", ALT_SOLAR)), ("wind 육지", w),
                    (f"wind {jeju_wind_name(d)} (not used)", series(d, "풍력", jeju_wind_name(d)))]:
        rows.append({"year": y, "profile": nm, "hours": len(ser), "annual_GWh": ser.sum() / 1000,
                     "max_MWh_per_h": ser.max(), "peak_normalised_CF_pct": 100 * ser.mean() / ser.max()})
save(rnd(pd.DataFrame(rows), 2), "re_profile_stats.csv")


def re_series(y, S, W, solar=None, wind="wind"):
    return S * prof[y][f"solar:{solar or BASE_SOLAR}"] + W * prof[y][wind]


# --------------------------------------------------------------- base grid
rows = []
for y in YEARS:
    for S, W in RE_LEVELS:
        re = re_series(y, S, W)
        for E in ESS_LEVELS:
            res, soc0, ec, ed = run(re, E, "base")
            rows.append(metrics(y, S, W, E, re, res, soc0, ec, ed))
grid_df = pd.DataFrame(rows)
save(rnd(grid_df), "re_ess_grid.csv")

# ------------------------------------------------------------- sensitivity
cases = [("base", dict(), "base")]
cases += [(f"solar {r}", dict(solar=r), "base") for r in SOLAR_ALTS]
cases += [(f"wind variability x{K_WIND:.2f} (Jeju-calibrated)", dict(wind="wind_inflated"), "base"),
          ("solar only, same RE energy", "solar_only", "base"),
          (f"alternative conventions (solar {ALT_SOLAR}, loss on discharge only, empty start)",
           dict(solar=ALT_SOLAR), "alternative")]
rows = []
for y in YEARS:
    for (S, W, E) in MAIN:
        for name, kw, conv in cases:
            if kw == "solar_only":
                tgt = re_series(y, S, W).sum()
                sol = prof[y][f"solar:{BASE_SOLAR}"]
                re = sol * tgt / sol.sum()
            else:
                re = re_series(y, S, W, **kw)
            res, soc0, ec, ed = run(re, E, conv)
            m = metrics(y, S, W, E, re, res, soc0, ec, ed)
            m["case"] = name
            rows.append(m)
sens = pd.DataFrame(rows)
lead = ["year", "solar_GW", "wind_GW", "ess_GWh", "case"]
save(rnd(sens[lead + [c for c in sens.columns if c not in lead]]), "re_ess_sensitivity.csv")

# ------------------------------------------- hourly file for the coincidence figure
for y in YEARS:
    S, W, E = MAIN[0]
    re = re_series(y, S, W)
    (direct, ch, dis, grid, curtail, soc), *_ = run(re, E, "base")
    idx = pd.date_range(f"{y}-01-01", periods=len(re), freq="h")
    h = pd.DataFrame({"hour_start": idx, "system_load_GW": sys_load.reindex(idx).values,
                      "system_reserve_GW": sys_reserve.reindex(idx).values, "re_GW": re,
                      "direct_GW": direct, "ess_charge_GW": ch, "ess_discharge_GW": dis,
                      "grid_draw_GW": grid, "soc_GWh": soc})
    save(rnd(h, 4), f"re_ess_hourly_{y}_S5W2.5_E8.csv")

save(pd.DataFrame({"item": ["base_solar_region", "after_dark_rule_pct", "min_annual_GWh", "K_WIND",
                            "cv_mainland_JanMay2024", "cv_jeju_JanMay2024"],
                   "value": [BASE_SOLAR, AFTER_DARK_MAX_PCT, MIN_ANNUAL_GWH, round(K_WIND, 4),
                             round(cv_main, 4), round(cv_jeju, 4)]}), "re_settings.csv")
print("done; base solar =", BASE_SOLAR, "; K_WIND =", round(K_WIND, 3))
