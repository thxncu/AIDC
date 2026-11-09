"""Robustness of the calibrated LOLE model to its main assumptions (Supplementary Tables S2 and S3).

Usage:  python run_lole_sensitivity.py <kpx_raw_dir> <re_dir> <results_dir>

Each variant is re-calibrated to the Plan's statement (LOLE 0.3 day/yr at a 13.1 % installed
reserve) with both calibration forms, then evaluated at the DC scenarios. Variants:
  base                      as in run_lole.py
  larger units              nuclear 1.4 GW, coal 1.0 GW, LNG 0.9 GW blocks
  smaller units             nuclear 1.0 GW, coal 0.5 GW, LNG 0.25 GW blocks
  uniform outage rate       4 % for every unit before calibration
  load year 2023/2024/2025  one load-shape year instead of the three-year average
  variable RE (2024-25)     RE no longer a firm 11.5 GW block: hydro+bio 1.49 GW firm, solar and
                            wind enter hour by hour (national traded solar, mainland wind), scaled
                            so their mean output in the 100 highest-load hours equals the Plan's
                            remaining summer effective RE (10.0 GW); load years 2024-2025
  base (2024-25)            base model on the same two load years, for comparison
  nuclear common-mode       a generic defect or regulatory order idles several reactors at once.
                            Precedent (NSSC press releases of 28 May 2013 and 2 Jan 2014): safety-
                            grade control cables with forged test certificates were found at
                            Shin-Kori 1-2 and Shin-Wolsong 1-2; the regulator ordered the operating
                            Shin-Kori 2 and Shin-Wolsong 1 shut down, extended the Shin-Kori 1
                            refuelling outage, and approved restart of the three units on
                            2 Jan 2014, 219 days later. Stylised as 3 GW (the three 1-GW-class
                            units) or 6 GW (twice the precedent) unavailable for 219 days once every
                            5, 10 or 20 years (12.0 %, 6.0 % or 3.0 % of days). The precedent gives
                            the size and duration of an event, not its frequency, so the recurrence
                            interval is an assumption and is varied. Calibration is NOT changed: the
                            Plan's standard is taken not to cover such events, so the result shows
                            the extra risk they add.
  fixed calibration         base calibration constants (outage multiplier or derate block of the base
                            case) held fixed while unit sizes, the outage-rate mix or the load year
                            change. These variants no longer reproduce the Plan's anchor; they show how
                            far the threshold moves when the structure changes without re-anchoring.
Also writes lole_scenario_points.csv (exact LOLE, LOLH and EUE at the Table 4 points),
lole_copt_mc_check.csv (the capacity outage table checked against 400,000 Monte Carlo draws of unit
outages) and lole_dc_profiles.csv: the base model with DC load shaped flat, as a stylised inference-type
diurnal cycle, or following the system load (upper bound), at the same annual energy.
"""
import glob
import os
import sys

import numpy as np
import pandas as pd
from scipy.optimize import brentq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402
from data import load_kpx  # noqa: E402
from flex import apply_flex  # noqa: E402

KPX_DIR, RE_DIR, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
STEP = 0.01
S_SUMMER = C.PLAN_SUMMER_EFFCAP_GW[2030]
D_PLAN = C.PLAN_TARGET_DEMAND_GW[2030]
D_CAL = S_SUMMER / (1 + C.PLAN_RM_2030["capacity_adequacy_LOLE"] / 100)
RE_SUMMER, CONV_SUMMER = 11.5, 124.1
RE_FIRM_VARIANT = 0.405 + 1.083            # hydro + biomass effective (Plan p.102)
SOLAR_NAMEPLATE, WIND_NAMEPLATE = 55.675, 18.281
SCEN = [3.7, 6.7, 11.7]
CM_DAYS = 219                              # 2013 precedent: 28 May 2013 - 2 Jan 2014
CM_SHARE = {T: CM_DAYS / (T * 365.25) for T in (5, 10, 20)}   # recurrence once every T years

BASE_FLEET = [("nuclear", 28.9, [1.4] * 10 + [1.0] * 14, 0.02), ("coal", 31.3, [1.0] * 18 + [0.5] * 26, 0.04),
              ("LNG", 58.8, [0.5] * 118, 0.04), ("pumped hydro", 5.2, [0.3] * 17, 0.03),
              ("new energy", 2.2, [0.1] * 22, 0.05), ("other", 0.4, [0.1] * 4, 0.05)]


def fleet(spec):
    scale = CONV_SUMMER / sum(f[1] for f in spec)
    steps, fors = [], []
    for _, gw, sizes, q in spec:
        sizes = np.array(sizes, float)
        target = gw * scale
        st = np.maximum(np.rint(sizes * target / sizes.sum() / STEP).astype(int), 1)
        st[-1] += int(round(target / STEP)) - st.sum()
        steps += list(st)
        fors += [q] * len(st)
    return np.array(steps), np.array(fors)


def copt(steps, fors, firm, mult=1.0, derate=0.0, cm=None):
    p = np.zeros(steps.sum() + 1)
    p[0] = 1.0
    top = 0
    for s, q in zip(steps, np.clip(fors * mult, 0, 0.95)):
        new = p * q
        new[s:top + s + 1] += p[:top + 1] * (1 - q)
        p, top = new, top + s
    if cm is not None:                       # (GW lost, probability): mixture with a shifted table
        k, pi = int(round(cm[0] / STEP)), cm[1]
        shifted = np.r_[p[k:], np.zeros(k)]
        shifted[0] += p[:k].sum()
        p = (1 - pi) * p + pi * shifted
    cap = np.arange(len(p)) * STEP + firm - derate
    edges = np.r_[cap - STEP / 2, cap[-1] + STEP / 2]
    F = np.r_[0.0, np.cumsum(p)]
    G = np.r_[0.0, np.cumsum((F[1:] + F[:-1]) / 2 * STEP)]
    return (edges, F, G), (cap * p).sum()


def eval_load(L, edges, F, G):
    lolp = np.interp(L, edges, F, left=0.0, right=1.0)
    k = np.clip(np.searchsorted(edges, L, side="right") - 1, 0, len(edges) - 2)
    part = G[k] + (F[k] + lolp) / 2 * (L - edges[k])
    eu = np.where(L < edges[0], 0.0, np.where(L <= edges[-1], part, G[-1] + (L - edges[-1])))
    return lolp, eu


def adjust(shape, peak, x, f=0.0, H=24, n_rebound=6):
    """Rule (a) of run_lole.py: curtail in the day's H highest-load hours, low-load recovery with
    the power limit, 24-hour deadline and energy recovery of flex.apply_flex."""
    L = shape * peak + x
    if f <= 0 or x <= 0:
        return L
    tops = [np.sort(np.arange(d, d + 24)[np.argsort(-L[d:d + 24])][:H]) for d in range(0, len(L), 24)]
    return apply_flex(L, tops, f * x, H, rebound="valley", n_rebound=n_rebound)


def avg_metrics(case, tabs, peak, x, **kw):
    out = []
    for y in case["years"]:
        L = adjust(case["shape"][y], peak, x, **kw) - case["vre"].get(y, 0.0)
        lolp, eu = eval_load(L, *tabs)
        lolp_d, _ = eval_load(L.reshape(-1, 24).max(axis=1), *tabs)
        out.append((lolp_d.sum(), lolp.sum(), eu.sum()))
    return np.mean(out, axis=0)


# -------------------------------------------------------------------- inputs
g, _ = load_kpx(KPX_DIR)
g["start"] = (g["datetime"] - pd.Timedelta("5min")).dt.floor("h")
hourly = g.groupby("start")["demand"].mean() / 1000
shape = {}
for y in [2023, 2024, 2025]:
    h = hourly.reindex(pd.date_range(f"{y}-01-01", f"{y}-12-31 23:00", freq="h")).interpolate(limit_direction="both")
    shape[y] = (h / h.max()).values

vre_raw = {}
for f in sorted(glob.glob(os.path.join(RE_DIR, "*.csv"))):
    d = pd.read_csv(f, encoding="cp949")
    d.columns = ["date", "hour", "region", "fuel", "mwh"]
    d["start"] = pd.to_datetime(d["date"]) + pd.to_timedelta(d["hour"].astype(int) - 1, unit="h")
    y = int(d["start"].dt.year.mode()[0])
    sol = d[d.fuel == "태양광"].groupby("start")["mwh"].sum().sort_index().values
    win = d[(d.fuel == "풍력") & (d.region == "육지")].set_index("start")["mwh"].sort_index().values
    vre_raw[y] = SOLAR_NAMEPLATE * sol / sol.max() + WIND_NAMEPLATE * win / win.max()


def vre_scaled(y, peak):
    """Scale hourly VRE so its mean output in the 100 highest gross-load hours = 10.0 GW."""
    top = np.argsort(-shape[y])[:100]
    return vre_raw[y] * (RE_SUMMER - RE_FIRM_VARIANT) / vre_raw[y][top].mean()


cases = {
    "base": dict(spec=BASE_FLEET, years=[2023, 2024, 2025]),
    "larger units": dict(spec=[("nuclear", 28.9, [1.4] * 21, 0.02), ("coal", 31.3, [1.0] * 31, 0.04),
                               ("LNG", 58.8, [0.9] * 65, 0.04)] + BASE_FLEET[3:], years=[2023, 2024, 2025]),
    "smaller units": dict(spec=[("nuclear", 28.9, [1.0] * 29, 0.02), ("coal", 31.3, [0.5] * 63, 0.04),
                                ("LNG", 58.8, [0.25] * 235, 0.04)] + BASE_FLEET[3:], years=[2023, 2024, 2025]),
    "uniform outage rate 4%": dict(spec=[(n, gw, s, 0.04) for n, gw, s, _ in BASE_FLEET], years=[2023, 2024, 2025]),
    "load year 2023 only": dict(spec=BASE_FLEET, years=[2023]),
    "load year 2024 only": dict(spec=BASE_FLEET, years=[2024]),
    "load year 2025 only": dict(spec=BASE_FLEET, years=[2025]),
    "base (load years 2024-25)": dict(spec=BASE_FLEET, years=[2024, 2025]),
    "variable RE (load years 2024-25)": dict(spec=BASE_FLEET, years=[2024, 2025], variable_re=True),
}
for T in (5, 10, 20):
    for gw in (3.0, 6.0):
        cases[f"nuclear common-mode {gw:.0f} GW, once every {T} years"] = dict(
            spec=BASE_FLEET, years=[2023, 2024, 2025], cm=(gw, CM_SHARE[T]))
# fixed-calibration variants: same structural changes, base calibration constants kept
for nm in ["larger units", "smaller units", "uniform outage rate 4%",
           "load year 2023 only", "load year 2024 only", "load year 2025 only"]:
    cases[f"{nm} (fixed calibration)"] = dict(cases[nm], fixed_cal=True)

base_par = {}
rows = []
for name, cs in cases.items():
    steps, fors = fleet(cs["spec"])
    firm = RE_FIRM_VARIANT if cs.get("variable_re") else RE_SUMMER
    case = {"years": cs["years"], "shape": shape, "vre": {}}
    if cs.get("variable_re"):
        case["vre"] = {y: vre_scaled(y, D_CAL) for y in cs["years"]}
    for cal in ["derate", "outage scaling"]:
        if cal == "derate":
            fn = lambda v: avg_metrics(case, copt(steps, fors, firm, derate=v)[0], D_CAL, 0)[0] - 0.3  # noqa: E731
            par = base_par[cal] if cs.get("fixed_cal") else brentq(fn, -20.0, 40.0, xtol=1e-5)
            tabs, mean_av = copt(steps, fors, firm, derate=par, cm=cs.get("cm"))
        else:
            fn = lambda v: avg_metrics(case, copt(steps, fors, firm, mult=v)[0], D_CAL, 0)[0] - 0.3  # noqa: E731
            par = base_par[cal] if cs.get("fixed_cal") else brentq(fn, 0.05, 15.0, xtol=1e-6)
            tabs, mean_av = copt(steps, fors, firm, mult=par, cm=cs.get("cm"))
        if name == "base":
            base_par[cal] = par
        r = {"variant": name, "calibration": cal,
             "calibration_mode": "fixed (base constants)" if cs.get("fixed_cal") else
             ("base calibration, event added" if cs.get("cm") else "re-calibrated"),
             "calibration_parameter": par,
             "implied_mean_availability_pct": 100 * mean_av / S_SUMMER,
             "LOLE_at_calibration_peak": avg_metrics(case, tabs, D_CAL, 0)[0],
             "LOLE_+0": avg_metrics(case, tabs, D_PLAN, 0)[0]}
        for x in SCEN:
            lole, lolh, eue = avg_metrics(case, tabs, D_PLAN, x)
            r[f"LOLE_+{x}"] = lole
            r[f"EUE_GWh_+{x}"] = eue
        try:      # negative: the variant exceeds LOLE 0.3 at the Plan's demand without DC excess
            r["dc_excess_at_LOLE_0.3"] = brentq(lambda x: avg_metrics(case, tabs, D_PLAN, x)[0] - 0.3,
                                                -15, 20, xtol=1e-4)
        except ValueError:
            r["dc_excess_at_LOLE_0.3"] = np.nan
        for x in [6.7, 11.7]:
            base = avg_metrics(case, tabs, D_PLAN, x)[0]
            fl = avg_metrics(case, tabs, D_PLAN, x, f=0.25, H=3)[0]
            try:
                efc = brentq(lambda b: avg_metrics(case, tabs, D_PLAN, x - b)[0] - fl, 0, x,
                             xtol=1e-4) if fl < base else 0
            except ValueError:
                efc = np.nan
            r[f"EFC_share_25pct_3h_lowload_+{x}"] = efc / (0.25 * x)
        rows.append(r)
        print(name, "|", cal, "|", ", ".join(f"{k}={float(v):.3f}" for k, v in r.items()
                                               if k not in ("variant", "calibration", "calibration_mode")))
res = pd.DataFrame(rows)
# availability is not comparable when RE leaves the firm block; blank it to avoid misuse
res.loc[res.variant.str.startswith("variable RE"), "implied_mean_availability_pct"] = np.nan
res.round(4).to_csv(os.path.join(OUT, "lole_sensitivity.csv"), index=False, encoding="utf-8-sig")


# ------------------------------------------------------------ DC load profile (Supplementary Table S3)
# Same annual energy as the flat block (mean = x), different hourly shapes, base fleet and both
# calibrations. Thresholds are reported in mean GW and in GW of DC load at the system's summer peak.
def dc_shape(kind, y):
    n = len(shape[y])
    hod = np.arange(n) % 24
    if kind == "flat (base case)":
        return np.ones(n)
    if kind == "inference-type diurnal (+-20%)":
        # stylised internet-traffic cycle: minimum 0.8 at 05:00, linear rise to 1.2 at 21:00, fall back
        up = (hod - 5) % 24
        return np.where(up <= 16, 0.8 + 0.4 * up / 16, 1.2 - 0.4 * (up - 16) / 8)
    if kind == "follows system load (upper bound)":
        return shape[y] / shape[y].mean()
    raise ValueError(kind)


PROFILES = ["flat (base case)", "inference-type diurnal (+-20%)", "follows system load (upper bound)"]
base_case = {"years": [2023, 2024, 2025], "shape": shape, "vre": {}}
steps, fors = fleet(BASE_FLEET)


def lole_profile(tabs, x, kind):
    out = []
    for y in base_case["years"]:
        L = shape[y] * D_PLAN + x * dc_shape(kind, y)
        lolp_d, _ = eval_load(L.reshape(-1, 24).max(axis=1), *tabs)
        lolp, eu = eval_load(L, *tabs)
        out.append((lolp_d.sum(), eu.sum()))
    return np.mean(out, axis=0)


rows = []
for cal in ["derate", "outage scaling"]:
    if cal == "derate":
        par = brentq(lambda v: avg_metrics(base_case, copt(steps, fors, RE_SUMMER, derate=v)[0], D_CAL, 0)[0] - 0.3,
                     -20.0, 40.0, xtol=1e-5)
        tabs = copt(steps, fors, RE_SUMMER, derate=par)[0]
    else:
        par = brentq(lambda v: avg_metrics(base_case, copt(steps, fors, RE_SUMMER, mult=v)[0], D_CAL, 0)[0] - 0.3,
                     0.05, 15.0, xtol=1e-6)
        tabs = copt(steps, fors, RE_SUMMER, mult=par)[0]
    for kind in PROFILES:
        # DC multiplier at the hour of each year's system peak, averaged over the load years
        at_peak = np.mean([dc_shape(kind, y)[np.argmax(shape[y])] for y in base_case["years"]])
        thr = brentq(lambda x: lole_profile(tabs, x, kind)[0] - 0.3, 0.0, 14.0, xtol=1e-4)
        r = {"profile": kind, "calibration": cal, "dc_multiplier_at_system_peak": at_peak,
             "threshold_mean_GW": thr, "threshold_at_system_peak_GW": thr * at_peak}
        for x in SCEN:
            lole, eue = lole_profile(tabs, x, kind)
            r[f"LOLE_+{x}"] = lole
            r[f"EUE_GWh_+{x}"] = eue
        rows.append(r)
        print("profile", kind, "|", cal, "|", {k: round(float(v), 3) for k, v in r.items() if k not in ("profile", "calibration")})
pd.DataFrame(rows).round(4).to_csv(os.path.join(OUT, "lole_dc_profiles.csv"), index=False, encoding="utf-8-sig")


# ------------------------------------------------------------ exact values at the scenario points (Table 4)
def metrics_flat(tabs, x):
    out = []
    for y in base_case["years"]:
        L = shape[y] * D_PLAN + x
        lolp_d, _ = eval_load(L.reshape(-1, 24).max(axis=1), *tabs)
        lolp, eu = eval_load(L, *tabs)
        out.append((lolp_d.sum(), lolp.sum(), eu.sum()))
    return np.mean(out, axis=0)


rows = []
for cal in ["derate", "outage scaling"]:
    if cal == "derate":
        par = brentq(lambda v: avg_metrics(base_case, copt(steps, fors, RE_SUMMER, derate=v)[0], D_CAL, 0)[0] - 0.3,
                     -20.0, 40.0, xtol=1e-5)
        tabs = copt(steps, fors, RE_SUMMER, derate=par)[0]
    else:
        par = brentq(lambda v: avg_metrics(base_case, copt(steps, fors, RE_SUMMER, mult=v)[0], D_CAL, 0)[0] - 0.3,
                     0.05, 15.0, xtol=1e-6)
        tabs = copt(steps, fors, RE_SUMMER, mult=par)[0]
    for x in [0.0, 0.36, 3.7, 6.7, 8.4, 11.7]:
        lole, lolh, eue = metrics_flat(tabs, x)
        rows.append({"calibration": cal, "dc_excess_GW": x, "installed_RM_pct": 100 * (S_SUMMER / (D_PLAN + x) - 1),
                     "LOLE_days_per_yr": lole, "LOLH_hours_per_yr": lolh, "EUE_GWh_per_yr": eue})

    # ---- check of the capacity outage table against Monte Carlo draws of unit outages (400,000 draws)
    q = np.clip(fors * (par if cal == "outage scaling" else 1.0), 0, 0.95)
    der = par if cal == "derate" else 0.0
    rng = np.random.default_rng(C.MC_SEED)
    sizes = steps * STEP
    caps = []
    for _ in range(8):                                     # 8 x 50,000 = 400,000 draws
        up = rng.random((50_000, len(sizes))) >= q
        caps.append(up @ sizes + RE_SUMMER - der)
    caps = np.concatenate(caps)
    for L in [D_CAL, D_PLAN + 8.4, D_PLAN + 11.7]:
        lolp_c, eu_c = eval_load(np.array([L]), *tabs)
        lolp_m = (caps < L).mean()
        eu_m = np.maximum(L - caps, 0).mean()
        se = np.sqrt(lolp_m * (1 - lolp_m) / len(caps))
        rows.append({"calibration": cal, "check": "COPT vs 400,000 Monte Carlo draws", "load_GW": L,
                     "LOLP_COPT": float(lolp_c[0]), "LOLP_MC": lolp_m, "LOLP_MC_se": se,
                     "EUP_GW_COPT": float(eu_c[0]), "EUP_GW_MC": eu_m})
res = pd.DataFrame(rows)
res[res.get("check").isna()].dropna(axis=1, how="all").round(4).to_csv(
    os.path.join(OUT, "lole_scenario_points.csv"), index=False, encoding="utf-8-sig")
res[res.get("check").notna()].dropna(axis=1, how="all").round(5).to_csv(
    os.path.join(OUT, "lole_copt_mc_check.csv"), index=False, encoding="utf-8-sig")
print(res.round(4).to_string())
