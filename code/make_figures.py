"""Figures of the article, drawn from results/*.csv.

Usage:  python make_figures.py <results_dir> <figures_dir>

Writes PDF (vector) and PNG (600 dpi) for:
  fig_mc_timeline        GPU Monte Carlo distribution and planning timeline (Fig. 1)
  fig_adequacy_headroom  installed reserve margin and LOLE vs unplanned DC load (Fig. 2)
  fig_residual_timing    when the RE+ESS residual grid draw occurs vs KPX electricity-market load (Fig. 3)
  fig_flex_duration      firm-capacity value of DC flexibility by curtailment duration (Fig. 4)
  fig_backcast           back-cast of the 83% availability rule at the summer peak hour, 2024-2026 (supporting plot; values in Table 5)
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

RES, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)

# colours: three categorical series colours, then text and grid tones
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df"
MM = 1 / 25.4
plt.rcParams.update({
    "font.family": "Inter", "font.size": 7.5, "axes.titlesize": 8, "axes.labelsize": 7.5,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7,
    "axes.edgecolor": GRID, "axes.linewidth": 0.6, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "xtick.major.size": 0, "ytick.major.size": 0,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5, "grid.linestyle": "-",
    "axes.spines.top": False, "axes.spines.right": False, "axes.titlelocation": "left",
    "axes.titlecolor": INK, "legend.frameon": False, "lines.solid_capstyle": "round",
    "pdf.fonttype": 42, "savefig.dpi": 600,
})


def finish(fig, name):
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(OUT, f"{name}.{ext}"), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def rd(name):
    return pd.read_csv(os.path.join(RES, name))


SCEN = [(3.7, "+3.7"), (6.7, "+6.7"), (11.7, "+11.7")]

# ------------------------------------------------ 1. headroom and LOLE (Fig. 2)
sw = rd("lole_dc_excess_sweep.csv")
hr = rd("headroom_plan_decomposition.csv")
fig, (a, b) = plt.subplots(1, 2, figsize=(190 * MM, 78 * MM), sharex=True)
fig.subplots_adjust(wspace=0.32)

rm = sw[sw.calibration == "derate"]
a.plot(rm.dc_excess_GW, rm.installed_RM_pct, color=S1, lw=1.5)
# threshold labels sit at the right edge (clear of the curve); headroom values beside each marker
thr = [("21.0%  applied standard", 21.0, "above", (5, 2), "left", "right"),
       ("20.1%  2030 computed standard", 20.1, "below", (5, 2), "left", "right"),
       ("14.0%  allowance used up", 14.0, "above", (5, 2), "left", "left"),
       ("13.1%  LOLE 0.3 days/yr level", 13.1, "above", (-6, -4), "right", "left")]
a.grid(axis="y", visible=False)
for lab, v, side, off, ha, where in thr:
    a.axhline(v, color=INK2, lw=0.7, ls=(0, (3, 2)), zorder=1)
    x_hit = float(hr.loc[np.isclose(hr.installed_RM_pct, v), "dc_headroom_GW"].iloc[0])
    a.plot([x_hit], [v], "o", ms=4.5, color=S1, mec="white", mew=1.0, zorder=4)
    a.annotate(lab, (11.95 if where == "right" else 0.15, v), xytext=(0, 2 if side == "above" else -2),
               textcoords="offset points", fontsize=6.3, color=INK2, ha=where,
               va="bottom" if side == "above" else "top")
    a.annotate(f"{x_hit:.1f} GW", (x_hit, v), xytext=off, textcoords="offset points", fontsize=6.5,
               color=INK, fontweight="bold", ha=ha, va="bottom" if off[1] > 0 else "top")
a.set_ylim(9, 23)
a.set_ylabel("Installed reserve margin, 2030 (%)")
a.set_title("(a) Headroom under the Plan's reserve accounting", pad=8)

for cal, col, lab in [("derate", S1, "Calibration: derate"),
                      ("outage scaling", S2, "Calibration: outage scaling")]:
    d = sw[(sw.calibration == cal) & (sw.LOLE_days_per_yr > 0)]
    b.plot(d.dc_excess_GW, d.LOLE_days_per_yr, color=col, lw=1.5, label=lab)
lo = sw.pivot(index="dc_excess_GW", columns="calibration", values="LOLE_days_per_yr")
b.fill_between(lo.index, lo.min(axis=1), lo.max(axis=1), color=S1, alpha=0.10, lw=0)
b.axhline(0.3, color=INK2, lw=0.7, ls=(0, (3, 2)))
b.annotate("Plan criterion LOLE 0.3 days/yr", (0.2, 0.3), xytext=(0, 3), textcoords="offset points",
           fontsize=6.5, color=INK2)
b.set_yscale("log")
b.yaxis.set_minor_locator(matplotlib.ticker.NullLocator())
b.set_ylim(1e-4, 10)
b.set_yticks([1e-4, 1e-3, 1e-2, 1e-1, 1, 10])
b.set_yticklabels(["0.0001", "0.001", "0.01", "0.1", "1", "10"])
b.set_ylabel("LOLE (days per year)")
b.set_title("(b) Calibrated probabilistic adequacy", pad=8)
b.legend(loc="lower right", handlelength=1.6)
for ax in (a, b):
    ax.set_xlim(0, 12)
    ax.set_xlabel("Unplanned DC peak load above the Plan's 3.3 GW (GW)")
    for x, lab in SCEN:
        ax.axvline(x, color="#c9c8c2", lw=0.5, zorder=0)
    ax.grid(axis="x", visible=False)
for x, lab in SCEN:
    a.annotate(lab + " GW", (x, 23), xytext=(0, -2), textcoords="offset points",
               fontsize=6, color=INK2, ha="right" if x > 11 else "center", va="top",
               bbox=dict(boxstyle="square,pad=0.15", fc="white", ec="none"))
finish(fig, "fig_adequacy_headroom")

# ------------------------------------------------ 2. flexibility value by duration (Fig. 4)
fx = rd("lole_flexibility.csv")
fx = fx[(fx.flex_share == 0.25)]
cats = [(3, "3 h"), (4, "4 h"), (6, "6 h")]
series = [("foresight", "valley", S1, "(a) Day's peak hours known; low-load recovery", -0.15),
          ("fixed", "valley", S2, "(b) Fixed monthly window; low-load recovery", 0.0),
          ("foresight", "after", S3, "(c) Day's peak hours known; immediate recovery", 0.15)]
fig, axes = plt.subplots(1, 2, figsize=(190 * MM, 72 * MM), sharey=True)
for ax, (x, lab) in zip(axes, [(6.7, "+6.7 GW"), (11.7, "+11.7 GW")]):
    d = fx[np.isclose(fx.dc_excess_GW, x)]
    pos = np.arange(len(cats) + 1)
    for sch, rb, col, name, off in series:
        mids, los, his = [], [], []
        for H, _ in cats:
            v = 100 * d[(d.duration_h == H) & (d.schedule == sch) & (d.rebound == rb)].efc_over_nominal.values
            mids.append(v.mean()), los.append(v.min()), his.append(v.max())
        mids, los, his = map(np.array, (mids, los, his))
        px = pos[:-1] + off
        ax.errorbar(px, mids, yerr=[mids - los, his - mids], fmt="o", ms=5, color=col, mec="white",
                    mew=1.0, elinewidth=1.2, capsize=0, label=name, zorder=3)
        m3 = mids[0]
        left = sch == "foresight" and rb == "valley"
        ax.annotate(f"{m3:.0f}%", (px[0], m3), xytext=(0, 6) if left else (5, 0), textcoords="offset points",
                    ha="center" if left else "left", va="bottom" if left else "center", fontsize=6.5, color=INK2)
    perm = 100 * d[d.duration_h == 24].efc_over_nominal.mean()
    ax.plot([pos[-1]], [perm], "o", ms=5, color=MUTED, mec="white", mew=1.0, zorder=3)
    ax.annotate(f"{perm:.0f}%", (pos[-1], perm), xytext=(0, 6), textcoords="offset points",
                ha="center", va="bottom", fontsize=6.5, color=INK2)
    ax.grid(axis="y", visible=False)
    for yv in (20, 40, 60, 80):
        ax.axhline(yv, color=GRID, lw=0.5, zorder=0)
    ax.axhline(100, color=INK2, lw=0.7, ls=(0, (3, 2)), zorder=1)
    ax.set_xticks(pos, [c[1] for c in cats] + ["No limit,\nno recovery"])
    ax.set_xlim(-0.5, len(pos) - 0.5)
    ax.set_ylim(0, 114)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.set_title(f"{lab}: 25% curtailment of the DC excess", pad=6)
    ax.set_xlabel("Maximum curtailment per day")
    ax.grid(axis="x", visible=False)
axes[0].set_ylabel("Firm-capacity equivalent\n(% of nominal curtailment)")
axes[1].annotate("Dashed line: 100% = curtailment counts in full as firm capacity", (-0.45, 3),
                 fontsize=6.3, color=INK2, va="bottom")
fig.legend(*axes[0].get_legend_handles_labels(), loc="upper center", bbox_to_anchor=(0.5, -0.05), ncols=3,
           fontsize=6.3, handletextpad=0.2, columnspacing=1.2)
finish(fig, "fig_flex_duration")

# ------------------------------------------------ 3. residual timing vs electricity-market load (Fig. 3)
fig, ax = plt.subplots(figsize=(120 * MM, 62 * MM))
w = 0.36
tops = []
for k, (y, col) in enumerate([(2024, S1), (2025, S2)]):
    h = rd(f"re_ess_hourly_{y}_S5W2.5_E8.csv").dropna(subset=["system_load_GW"])
    h["dec"] = pd.qcut(h.system_load_GW.rank(method="first"), 10, labels=False) + 1
    share = 100 * h.groupby("dec").grid_draw_GW.sum() / h.grid_draw_GW.sum()
    ax.bar(share.index + (k - 0.5) * (w + 0.04), share.values, width=w, color=col, label=str(y), zorder=3)
    tops.append(share.loc[10])
ax.axhline(10, color=INK2, lw=0.7, ls=(0, (3, 2)), zorder=2)
ax.annotate("10% = spread evenly", (10.45, 10), xytext=(0, 3), textcoords="offset points",
            ha="right", fontsize=6.5, color=INK2)
ax.annotate(f"Top decile: {tops[0]:.1f}% / {tops[1]:.1f}%", (10, max(tops) + 0.3),
            xytext=(10.45, 7.0), textcoords="data", ha="right", va="bottom", fontsize=6.5, color=INK,
            arrowprops=dict(arrowstyle="-", color=INK2, lw=0.5, shrinkA=1, shrinkB=1))
ax.set_xticks(range(1, 11), [str(i) for i in range(1, 11)])
ax.set_xlabel("Electricity-market load decile (1 = lowest-load hours, 10 = highest-load hours)")
ax.set_ylabel("Share of annual grid draw (%)")
ax.set_title("Grid draw of a 1 GW DC with 5 GW solar + 2.5 GW wind + 8 GWh storage", pad=6)
ax.legend(loc="upper right", ncols=2)
ax.grid(axis="x", visible=False)
finish(fig, "fig_residual_timing")

# ------------------------------------------------ 4. back-cast, 2024-2026 (2026 out of sample)
pk = rd("oos_2026_summer_peak_backcast.csv")
pk = pk[pk.year >= 2024].reset_index(drop=True)
avs4 = rd("availability_2023_2026.csv")
avs4 = avs4[avs4.year >= 2024].reset_index(drop=True)
fig, (a, b) = plt.subplots(1, 2, figsize=(190 * MM, 70 * MM))
fig.subplots_adjust(wspace=0.30)
xs = np.arange(len(pk))
for ax in (a, b):
    ax.axvspan(xs[-1] - 0.5, xs[-1] + 0.5, color="#f3f2ee", zorder=0, lw=0)
    ax.set_xticks(xs, [str(y) for y in pk.year])
    ax.set_xlim(-0.5, len(xs) - 0.5)
    ax.grid(axis="x", visible=False)
series = [("KPX observed", "actual_RM_pct", S1, -0.18), ("Rule, actual peak demand (ex post)", "expost_RM_83pct", S2, 0.0),
          ("Rule, Plan market-basis target (ex ante)", "exante_RM_83pct_market", S3, 0.18)]
for name, col_, col, off in series:
    ys = pk[col_].values
    a.plot(xs + off, ys, "o", ms=5.5, color=col, mec="white", mew=1.0, label=name, zorder=3)
    for xi, yi in zip(xs + off, ys):
        a.annotate(f"{yi:.1f}", (xi, yi), xytext=(0, 5), textcoords="offset points", ha="center", fontsize=6.3, color=INK2)
a.set_ylim(-1, 15)
a.set_ylabel("Reserve margin at the summer peak (%)")
a.set_title("(a) Reserve at the summer peak hour: observed vs 83% rule", pad=6)
a.legend(loc="upper left", ncols=1, fontsize=6.3, handletextpad=0.2)
for ax_, ytop in ((a, 14.6), (b, 88.8)):
    ax_.annotate("out of sample", (xs[-1], ytop), ha="center", va="top", fontsize=6.3, color=INK2)
for name, ys, col, off in [("Top-20 summer days, mean", avs4.top20_mean.values, S1, -0.1),
                           ("Summer peak hour", pk.availability_at_peak_pct.values, S2, 0.1)]:
    b.plot(xs + off, ys, "o", ms=5.5, color=col, mec="white", mew=1.0, label=name, zorder=3)
    left = col == S1
    for xi, yi in zip(xs + off, ys):
        b.annotate(f"{yi:.1f}", (xi, yi), xytext=(-6, 0) if left else (0, 5), textcoords="offset points",
                   ha="right" if left else "center", va="center" if left else "bottom", fontsize=6.3, color=INK2)
b.axhline(83, color=INK2, lw=0.7, ls=(0, (3, 2)), zorder=1)
b.annotate("83% rule", (0.5, 83), xytext=(0, 3), textcoords="offset points", ha="center", fontsize=6.3, color=INK2)
b.set_ylim(78, 89)
b.set_ylabel("KPX supply capacity / Plan summer\neffective capacity (%)")
b.set_title("(b) Availability on the Plan's summer denominator", pad=6)
b.legend(loc="lower left", ncols=1, fontsize=6.3, handletextpad=0.2)
finish(fig, "fig_backcast")

# ------------------------------------------------ 5. Monte Carlo and planning timeline (Fig. 1)
mc = rd("monte_carlo_draws_independent.csv").gpu_MW.values
med, p5, p95 = np.median(mc), np.percentile(mc, 5), np.percentile(mc, 95)
fig = plt.figure(figsize=(190 * MM, 80 * MM))
a = fig.add_axes([0.06, 0.16, 0.30, 0.70])
b = fig.add_axes([0.44, 0.16, 0.55, 0.70])
a.hist(mc, bins=np.arange(100, 760, 15), color=S1, alpha=0.85, lw=0, zorder=3)
a.axvline(med, color=S2, lw=1.4, zorder=4)
for v in (p5, p95):
    a.axvline(v, color=INK2, lw=0.8, ls=(0, (3, 2)), zorder=4)
a.annotate(f"Median {med:.0f} MW", (med, a.get_ylim()[1]), xytext=(4, -2), textcoords="offset points",
           fontsize=6.5, color=INK, va="top")
a.annotate(f"5th\u201395th percentile\n{p5:.0f}\u2013{p95:.0f} MW", (p95, a.get_ylim()[1] * 0.62), xytext=(4, 0),
           textcoords="offset points", fontsize=6.3, color=INK2, va="top")
a.set_xlim(100, 760)
a.set_xlabel("GPU-attributable power (MW)")
a.set_ylabel("Draws (of 10,000)")
a.set_title("(a) 260,000-GPU program (Table 2)", pad=6)
a.grid(axis="x", visible=False)
ev = [("2023-08-31", "Plan's DC data reference\n(KEPCO requests to Aug 2023)", S1, 1),
      ("2024-05-31", "11th Plan working-\ngroup draft", S1, -1),
      ("2025-02-21", "11th Plan adopted\n(DC 3.3 GW in 2030)", S1, 1.9),
      ("2025-06-26", "IDC Korea forecast", MUTED, -1.9),
      ("2025-10-31", "260,000-GPU\nannouncement (APEC)", S2, 1),
      ("2026-04-22", "12th Plan outlook:\nAI-DC +4.0 GW by 2040", S3, -1),
      ("2026-08-20", "Provisional re-forecast:\n+11.9 GW by 2040;\ncut signaled Oct 2026", S3, 2.2)]
t = [pd.Timestamp(e[0]) for e in ev]
t0 = pd.Timestamp("2023-06-01")
xv = [(d - t0).days / 30.44 for d in t]
b.axhline(0, color=INK2, lw=0.8, zorder=1)
for (d, lab, col, h), x in zip(ev, xv):
    b.plot([x, x], [0, h * 0.82], color=GRID if col == MUTED else col, lw=0.7, zorder=2)
    b.plot([x], [0], "o", ms=5, color=col, mec="white", mew=1.0, zorder=3)
    b.annotate(f"{pd.Timestamp(d):%b %Y}\n" + lab, (x, h * 0.85), ha="center", va="bottom" if h > 0 else "top",
               fontsize=6.1, color=INK if col != MUTED else INK2, linespacing=1.15)
def brace(x1, x2, y, txt):
    b.annotate("", (x1, y), (x2, y), arrowprops=dict(arrowstyle="<->", color=INK2, lw=0.6, shrinkA=0, shrinkB=0))
    b.annotate(txt, ((x1 + x2) / 2, y), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom",
               fontsize=6.1, color=INK2)
brace(xv[0], xv[2], -3.25, "18 months: data age at adoption")
brace(xv[2], xv[4], 3.6, "8 months")
b.set_ylim(-3.6, 4.5)
b.set_xlim(-1, 46.5)
b.set_yticks([])
b.set_xticks([(pd.Timestamp(f"{y}-01-01") - t0).days / 30.44 for y in (2024, 2025, 2026)], ["2024", "2025", "2026"])
b.grid(False)
for sp in ("left", "bottom"):
    b.spines[sp].set_visible(False)
b.set_title("(b) Planning timeline", pad=6)
finish(fig, "fig_mc_timeline")

print("figures written to", OUT)
