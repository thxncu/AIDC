"""Probabilistic adequacy (LOLE, LOLH, EUE) for 2030 with unplanned DC load.

Usage:  python run_lole.py <kpx_raw_dir> <results_dir>

Approach
  The Plan states (p.43) that, for 2030, an installed reserve of 13.1 % meets the
  reliability criterion LOLE = 0.3 day/yr (model RASMO; unit inputs not published).
  The script builds a capacity outage probability table (COPT) for the 2030 summer fleet
  and calibrates it so it reproduces that statement: LOLE = 0.3 day/yr when the 2030 fleet
  (135.6 GW) serves a peak of 135.6 / 1.131 = 119.9 GW. Two calibrations represent two
  plausible structures for the unknown inputs (they do not span the full uncertainty):
    (i)  "outage scaling": all unit forced-outage rates multiplied by a common factor;
    (ii) "derate":         base outage rates plus a fixed unavailable block (GW).
  The calibrated model is then run at the Plan's demand (111.4 GW) plus a flat DC excess x.

Load: KPX hourly mean demand 2023, 2024, 2025 (three weather/load-shape years), each
  scaled so that its annual hourly peak equals the demand being tested.
Fleet: Plan p.51 year-end 2030 effective capacity by source (non-RE 126.8 GW), scaled to
  the p.50 summer conventional total (124.1 GW); RE at its summer effective value
  (11.5 GW) as a firm block, as in the Plan's effective-capacity accounting.
DC flexibility: a share f of the DC excess is curtailed for H hours a day under three
  operating rules; the deferred work is recovered under a power limit, a 24-hour deadline and
  full energy recovery (see flex.py).
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy.optimize import brentq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402
from data import load_kpx  # noqa: E402
from flex import apply_flex  # noqa: E402

KPX_DIR, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
STEP = 0.01                       # GW grid for the COPT
S_SUMMER = C.PLAN_SUMMER_EFFCAP_GW[2030]
D_PLAN = C.PLAN_TARGET_DEMAND_GW[2030]
RM_LOLE = C.PLAN_RM_2030["capacity_adequacy_LOLE"] / 100
D_CAL = S_SUMMER / (1 + RM_LOLE)
LOLE_TARGET = 0.3
RE_SUMMER = 11.5
CONV_SUMMER = 124.1


def save(df, name):
    df.to_csv(os.path.join(OUT, name), index=False, encoding="utf-8-sig")


# ------------------------------------------------------------------- fleet
# (source, year-end 2030 effective GW (Plan p.51), unit sizes GW, base forced-outage rate)
# Unit sizes and outage rates are representative assumptions (the Plan does not publish
# RASMO inputs); the calibration absorbs their overall level.
FLEET = [
    ("nuclear", 28.9, [1.4] * 10 + [1.0] * 14, 0.02),
    ("coal", 31.3, [1.0] * 18 + [0.5] * 26, 0.04),
    ("LNG", 58.8, [0.5] * 118, 0.04),
    ("pumped hydro", 5.2, [0.3] * 17, 0.03),
    ("new energy", 2.2, [0.1] * 22, 0.05),
    ("other", 0.4, [0.1] * 4, 0.05),
]
nonre_yearend = sum(f[1] for f in FLEET)
scale = CONV_SUMMER / nonre_yearend
steps, fors, fleet_rows = [], [], []
for name, gw, sizes, q in FLEET:
    sizes = np.array(sizes, float)
    target = gw * scale                              # this source's share of the summer total
    st = np.maximum(np.rint(sizes * target / sizes.sum() / STEP).astype(int), 1)
    st[-1] += int(round(target / STEP)) - st.sum()   # put the rounding residual on one unit
    steps += list(st)
    fors += [q] * len(st)
    fleet_rows.append({"source": name, "yearend_2030_effective_GW": gw, "summer_GW_used": st.sum() * STEP,
                       "units": len(st), "unit_size_GW": round(st.mean() * STEP, 3), "base_FOR": q})
fleet_rows.append({"source": "renewables (firm block)", "yearend_2030_effective_GW": 9.9,
                   "summer_GW_used": RE_SUMMER, "units": 1, "unit_size_GW": RE_SUMMER, "base_FOR": 0.0})
steps, fors = np.array(steps), np.array(fors)
units = steps * STEP
assert abs(units.sum() + RE_SUMMER - S_SUMMER) < 0.03, units.sum() + RE_SUMMER
save(pd.DataFrame(fleet_rows).round(3), "lole_fleet.csv")


def copt(mult=1.0, derate=0.0):
    """Probability mass of available conventional capacity on the STEP grid."""
    p = np.zeros(steps.sum() + 1)
    p[0] = 1.0
    top = 0
    for s, q in zip(steps, np.clip(fors * mult, 0, 0.95)):
        new = p.copy() * q
        new[s:top + s + 1] += p[:top + 1] * (1 - q)
        p = new
        top += s
    cap = np.arange(len(p)) * STEP + RE_SUMMER - derate
    return cap, p


def risk_tables(cap, p):
    """Each probability mass is spread uniformly over +-STEP/2 so that LOLP(L) is
    piecewise linear in L and EUE(L) = integral of LOLP is smooth; this keeps the
    calibration root-finding well behaved."""
    edges = np.r_[cap - STEP / 2, cap[-1] + STEP / 2]
    F = np.r_[0.0, np.cumsum(p)]                     # P(A < edge)
    G = np.r_[0.0, np.cumsum((F[1:] + F[:-1]) / 2 * STEP)]   # integral of F up to edge
    return edges, F, G


def eval_load(L, edges, F, G):
    """LOLP = P(A < L) and expected unserved power E[(L - A)+] for loads L (GW)."""
    L = np.asarray(L, float)
    lolp = np.interp(L, edges, F, left=0.0, right=1.0)
    k = np.clip(np.searchsorted(edges, L, side="right") - 1, 0, len(edges) - 2)
    inside = (L >= edges[0]) & (L <= edges[-1])
    part = G[k] + (F[k] + lolp) / 2 * (L - edges[k])
    eu = np.where(L < edges[0], 0.0, np.where(inside, part, G[-1] + (L - edges[-1])))
    return lolp, eu


# -------------------------------------------------------------------- load
g, _ = load_kpx(KPX_DIR)
g["start"] = (g["datetime"] - pd.Timedelta("5min")).dt.floor("h")
hourly = g.groupby("start")["demand"].mean() / 1000
shapes = {}
gap_log = {}
for y in sorted(hourly.index.year.unique()):
    idx = pd.date_range(f"{y}-01-01", f"{y}-12-31 23:00", freq="h")
    obs = hourly.reindex(idx)
    if obs.notna().mean() < 0.98:      # skip partial years (e.g., the single 2022-12-31 23:00 hour)
        continue
    gap_log[y] = int(obs.isna().sum())
    h = obs.interpolate(limit_direction="both")
    shapes[y] = h / h.max()
YEARS = sorted(shapes)
assert YEARS == [2023, 2024, 2025], YEARS


def fixed_windows(H, top_share=0.2):
    """Month -> start hour of the H consecutive hours with the highest average load on
    that month's high-load days (top 20 % of days by daily peak, pooled over the three
    load years). A seasonal schedule an operator could publish in advance; it needs no
    knowledge of any particular day's peak hour."""
    pooled = pd.concat([s for s in shapes.values()])
    days = pooled.groupby(pooled.index.normalize()).max()
    out = {}
    for m in range(1, 13):
        dm = days[days.index.month == m]
        hot = dm[dm >= dm.quantile(1 - top_share)].index
        sel = pooled[pooled.index.normalize().isin(hot)]
        v = sel.groupby(sel.index.hour).mean().values
        out[m] = int(np.argmax([v[s:s + H].sum() for s in range(0, 24 - H + 1)]))
    return out


WINDOWS = {H: fixed_windows(H) for H in (3, 4, 6)}


def adjust(shape, peak, x, f=0.0, H=24, rebound="valley", n_rebound=6, schedule="foresight", stats=None):
    """Hourly load (GW): scaled shape + flat DC excess, with DC flexibility.

    A share f of the DC excess is curtailed for H hours a day.
      schedule="foresight": in the H highest-load hours of each day (perfect knowledge
                            of the day's load ranking; optimistic; rules (a) and (c))
      schedule="fixed":     in a fixed monthly window estimated from the 2023-2025 load data
                            (see fixed_windows; no daily foresight; rule (b))
    Recovery of the deferred work follows flex.apply_flex: low-load recovery (rebound="valley",
    rules (a) and (b)) or immediate recovery (rebound="after", rule (c)), with a recovery-power
    limit of f*x*H/6, a 24-hour deadline from each job's curtailment and full energy recovery.
    With H = 24 the reduction is permanent (no recovery).
    """
    L = shape.values * peak + x
    if f <= 0 or x <= 0:
        return L
    n = len(L)
    months = shape.index.month
    tops = []
    for d in range(0, n, 24):
        ii = np.arange(d, min(d + 24, n))
        if schedule == "fixed" and H < 24:
            s0 = WINDOWS[H][months[d]]
            top = ii[s0:s0 + H]
        else:
            top = ii[np.argsort(-L[ii])][:H]
        tops.append(np.sort(top))
    return apply_flex(L, tops, f * x, H, rebound=rebound, n_rebound=n_rebound, stats=stats)


def metrics(L, idx, edges, F, G):
    lolp, eu = eval_load(L, edges, F, G)
    day = pd.Series(L, index=idx).groupby(idx.normalize()).max()
    lolp_d, _ = eval_load(day.values, edges, F, G)
    return lolp_d.sum(), lolp.sum(), eu.sum()        # LOLE days/yr, LOLH h/yr, EUE GWh/yr


def avg_metrics(peak, x, edges, F, G, **kw):
    vals = [metrics(adjust(shapes[y], peak, x, **kw), shapes[y].index, edges, F, G) for y in YEARS]
    return np.mean(vals, axis=0)


# ------------------------------------------------------------- calibration
def lole_at_cal(**kw):
    cap, p = copt(**kw)
    return avg_metrics(D_CAL, 0.0, *risk_tables(cap, p))[0]


calib = {}
calib["outage scaling"] = {"mult": brentq(lambda m: lole_at_cal(mult=m) - LOLE_TARGET, 1.0, 12.0, xtol=1e-6),
                           "derate": 0.0}
calib["derate"] = {"mult": 1.0, "derate": brentq(lambda d: lole_at_cal(derate=d) - LOLE_TARGET, 0.0, 30.0, xtol=1e-6)}
rows = []
models = {}
for name, kw in calib.items():
    cap, p = copt(**kw)
    models[name] = risk_tables(cap, p)
    mean_avail = (cap * p).sum()
    rows.append({"calibration": name, "FOR_multiplier": kw["mult"], "derate_GW": kw["derate"],
                 "LOLE_at_calibration_peak": avg_metrics(D_CAL, 0, *models[name])[0],
                 "calibration_peak_GW": D_CAL,
                 "mean_available_GW": mean_avail,
                 "implied_mean_availability_pct": 100 * mean_avail / S_SUMMER,
                 "weighted_FOR_pct": 100 * (units * np.clip(fors * kw["mult"], 0, 0.95)).sum() / units.sum()})
save(pd.DataFrame(rows).round(4), "lole_calibration.csv")

# --------------------------------------------------------- DC excess sweep
xs = np.round(np.arange(0, 12.01, 0.25), 2)
rows = []
for name, (edges, F, G) in models.items():
    for x in xs:
        lole, lolh, eue = avg_metrics(D_PLAN, x, edges, F, G)
        rows.append({"calibration": name, "dc_excess_GW": x,
                     "installed_RM_pct": 100 * (S_SUMMER / (D_PLAN + x) - 1),
                     "LOLE_days_per_yr": lole, "LOLH_hours_per_yr": lolh, "EUE_GWh_per_yr": eue})
sweep = pd.DataFrame(rows)
save(sweep.round(5), "lole_dc_excess_sweep.csv")

# x at which LOLE reaches 0.3 with a flat DC load (vs 8.49 GW for proportional growth)
rows = []
for name, (edges, F, G) in models.items():
    f = lambda x: avg_metrics(D_PLAN, x, edges, F, G)[0] - LOLE_TARGET  # noqa: E731
    rows.append({"calibration": name, "dc_excess_at_LOLE_0.3_GW": brentq(f, 0.0, 12.0, xtol=1e-4),
                 "plan_decomposition_value_GW": S_SUMMER / (1 + RM_LOLE) - D_PLAN})
save(pd.DataFrame(rows).round(3), "lole_threshold.csv")

# --------------------------------------------------- flexibility with duration
FLEX = [0.15, 0.25, 0.40]
DUR = [3, 4, 6, 24]
SCEN = [3.7, 6.7, 11.7]


def efc(target_lole, x, edges, F, G):
    """Firm capacity (GW, perfectly available) that gives the same LOLE as the
    flexibility case; negative when the flexibility case is worse than none."""
    base = avg_metrics(D_PLAN, x, edges, F, G)[0]
    if abs(target_lole - base) < 1e-12:
        return 0.0
    # a perfectly available block of b GW lowers net load by b in every hour
    g_ = lambda b: avg_metrics(D_PLAN, x - b, edges, F, G)[0] - target_lole  # noqa: E731
    lo, hi = (0.0, x + 1.0) if target_lole < base else (-(x + 1.0), 0.0)
    try:
        return brentq(g_, lo, hi, xtol=1e-4)
    except ValueError:
        return np.nan


rows = []
for name, (edges, F, G) in models.items():
    for x in SCEN:
        base = avg_metrics(D_PLAN, x, edges, F, G)
        rows.append({"calibration": name, "dc_excess_GW": x, "flex_share": 0.0, "duration_h": 0,
                     "schedule": "none", "rebound": "none", "LOLE_days_per_yr": base[0],
                     "LOLH_hours_per_yr": base[1],
                     "EUE_GWh_per_yr": base[2], "LOLE_reduction_pct": 0.0,
                     "firm_capacity_equivalent_GW": 0.0, "nominal_reduction_GW": 0.0})
        for f in FLEX:
            for H in DUR:
                combos = ([("foresight", "valley"), ("foresight", "after"), ("fixed", "valley")] if H < 24
                          else [("permanent", "none (permanent)")])
                for sch, rb in combos:
                    kw = dict(f=f, H=H, rebound=rb, schedule=sch) if H < 24 else dict(f=f, H=H)
                    m = avg_metrics(D_PLAN, x, edges, F, G, **kw)
                    st_y = []
                    for y in YEARS:
                        st = {}
                        adjust(shapes[y], D_PLAN, x, stats=st, **kw)
                        st_y.append(st)
                    rows.append({"calibration": name, "dc_excess_GW": x, "flex_share": f, "duration_h": H,
                                 "schedule": sch, "rebound": rb, "LOLE_days_per_yr": m[0],
                                 "LOLH_hours_per_yr": m[1],
                                 "EUE_GWh_per_yr": m[2],
                                 "LOLE_reduction_pct": 100 * (1 - m[0] / base[0]) if base[0] > 0 else np.nan,
                                 "firm_capacity_equivalent_GW": efc(m[0], x, edges, F, G),
                                 "nominal_reduction_GW": f * x,
                                 "delivered_share_of_nominal_energy": np.mean([t["delivered_share"] for t in st_y]),
                                 "days_depth_reduced_per_yr": np.mean([t["days_reduced"] for t in st_y]),
                                 "days_not_called_per_yr": np.mean([t["days_skipped"] for t in st_y]),
                                 "max_recovery_over_cap": max(t["max_recovery_GW"] / t["recovery_cap_GW"]
                                                              if t["recovery_cap_GW"] > 0 else 0 for t in st_y),
                                 "max_delay_h": max(t["max_delay_h"] for t in st_y)})
flex = pd.DataFrame(rows)
flex["efc_over_nominal"] = np.where(flex.nominal_reduction_GW > 0,
                                    flex.firm_capacity_equivalent_GW / flex.nominal_reduction_GW, np.nan)
save(flex.round(4), "lole_flexibility.csv")
save(pd.DataFrame([{"duration_h": H, "month": m, "window_start_hour": s, "window_end_hour": s + H}
                   for H, w in WINDOWS.items() for m, s in w.items()]), "lole_fixed_windows.csv")
print(pd.read_csv(os.path.join(OUT, "lole_calibration.csv")).to_string(index=False))
print(pd.read_csv(os.path.join(OUT, "lole_threshold.csv")).to_string(index=False))
