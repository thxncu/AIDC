"""Duration-limited DC flexibility with recovery of deferred work (shared by run_lole.py and
run_lole_sensitivity.py).

Each day, a share f of the DC excess x is curtailed in the day's curtailment hours (`tops`, H hours).
The deferred work is recovered under three constraints that the code enforces and checks:

  power    recovery adds at most  cap = f * x * H / n_rebound  GW in any hour, the spare server and
           connection capacity needed to recover a full day's deferral in n_rebound (= 6) hours;
  timing   recovery hours come after the day's last curtailed hour, before the next day's first
           curtailed hour, and no later than `deadline` (= 24) hours after the day's FIRST curtailed
           hour, so every deferred job finishes within 24 hours of its own curtailment;
  energy   all curtailed energy is recovered.

The recovery hours are the n_rebound lowest-load eligible hours (rebound="valley", low-load recovery)
or the first n_rebound eligible hours (rebound="after", immediate recovery). When only m < n_rebound
eligible hours exist (a late window followed by an early window the next day, or the last day of the
year), the day's curtailment depth is scaled by m / n_rebound so that the deferred work still fits
under the power limit; with m = 0 the day is not called. Curtailed and recovered energy are therefore
equal every day, the recovery power never exceeds the limit, and no backlog carries over.
With H >= 24 the reduction is permanent (no recovery).
"""
import numpy as np

N_REBOUND = 6
DEADLINE_H = 24


def apply_flex(L, tops, red, H, rebound="valley", n_rebound=N_REBOUND, deadline=DEADLINE_H, stats=None):
    """Return the hourly load after curtailment and recovery.

    L      hourly load (GW) including the flat DC excess
    tops   list of arrays: the curtailment hours of each day (absolute hour indices)
    red    nominal curtailment f * x (GW)
    stats  optional dict, filled with checks and counts
    """
    Ld = L.astype(float).copy()
    n = len(L)
    if H >= 24:
        for top in tops:
            Ld[top] -= red
        if stats is not None:
            stats.update(days=len(tops), days_reduced=0, days_skipped=0, delivered_share=1.0,
                         max_recovery_GW=0.0, recovery_cap_GW=0.0, max_delay_h=0, energy_residual_GWh=0.0)
        return Ld
    cap = red * H / n_rebound
    reduced = skipped = 0
    nominal = delivered = 0.0
    max_add = 0.0
    max_delay = 0
    for k, top in enumerate(tops):
        first, last = int(top.min()), int(top.max())
        nxt = int(tops[k + 1].min()) if k + 1 < len(tops) else n
        cand = np.arange(last + 1, min(first + deadline + 1, nxt, n))
        if rebound == "valley":
            rec = cand[np.argsort(L[cand], kind="stable")][:n_rebound]
        elif rebound == "after":
            rec = cand[:n_rebound]
        else:
            raise ValueError(rebound)
        m = len(rec)
        scale = m / n_rebound
        nominal += red * len(top)
        if m == 0:
            skipped += 1
            continue
        if m < n_rebound:
            reduced += 1
        Ld[top] -= red * scale
        Ld[rec] += cap                      # cap * m == red * scale * H
        delivered += red * scale * len(top)
        max_delay = max(max_delay, int(rec.max()) - first)
    added = np.maximum(Ld - L, 0.0)
    max_add = float(added.max()) if len(added) else 0.0
    residual = float((Ld - L).sum())
    # checks: energy conserved, power limit respected, deadline met
    assert abs(residual) < 1e-6 * max(1.0, red * H * len(tops)), residual
    assert max_add <= cap + 1e-9, (max_add, cap)
    assert max_delay <= deadline, max_delay
    if stats is not None:
        stats.update(days=len(tops), days_reduced=reduced, days_skipped=skipped,
                     delivered_share=delivered / nominal if nominal > 0 else 1.0,
                     max_recovery_GW=max_add, recovery_cap_GW=cap, max_delay_h=max_delay,
                     energy_residual_GWh=residual)
    return Ld
