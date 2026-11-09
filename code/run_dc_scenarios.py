"""DC demand scenarios in one unit: contribution to the national summer peak (GW), the Plan's unit (p.23).

Usage:  python run_dc_scenarios.py <results_dir>

Writes the scenarios of Table 3. IDC Korea total DC power and the Plan's DC demand are different
quantities: IDC reports facility power, while the Plan's 3.3 GW is the DC contribution to the 2030 summer
peak. In 2025 the IDC figure (4.46 GW) is 3.7 times the Plan's DC summer peak for the same year (1.2 GW).
The excess levels (+3.7, +6.7, +11.7 GW) are therefore stress levels of DC summer peak above the Plan,
and each is stated in the Plan's own terms:
  - total DC summer peak in 2030, against the Plan's own trajectory (6.2 GW in 2038);
  - the contracted DC capacity it implies, using the Plan's ratio of peak increment to contracted capacity
    judged suppliable (p.22-23) and, as an upper-utilisation bound, 0.7 for AI facilities (assumption).
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)

supp27 = C.PLAN_DC_CONTRACT_SUPPLIABLE_MW[2027] / 1000
r_incr = C.PLAN_DC_PEAK_INCREMENT_GW[2027] / supp27                                   # 1.5 / 4.718
r_total = (C.PLAN_DC_PEAK_TOTAL_GW[2027] - C.PLAN_DC_PEAK_TOTAL_GW[2023]) / supp27     # 1.7 / 4.718
R_AI = 0.70
idc_ratio_2025 = C.IDC_DC_POWER_MW[2025] / 1000 / C.PLAN_DC_PEAK_TOTAL_GW[2025]

# GPU programme: Monte Carlo result of run_all.py (Table 2 specification, independent inputs, full realization)
mc = pd.read_csv(os.path.join(OUT, "monte_carlo_gpu_increment.csv"))
mc = mc[(mc["variant"] == "independent") & (mc["realization"] == 1.0)].iloc[0]
GPU_MEDIAN, GPU_P5, GPU_P95 = mc["median_MW"] / 1000, mc["p5_MW"] / 1000, mc["p95_MW"] / 1000

# Contracts that the Plan's 2030 DC trajectory already implies. The Plan counts the 4.718 GW judged
# suppliable to 2027 and extends the request trend from 2028 (p.22-23), so new contracts first fill
# this trajectory before they add to it.
plan_contracts_2030_total = (C.PLAN_DC_2030_GW - C.PLAN_DC_PEAK_TOTAL_GW[2023]) / r_total   # 2.7 / r_total
plan_contracts_2030_incr = C.PLAN_DC_PEAK_INCREMENT_GW[2030] / r_incr                      # 2.3 / r_incr
plan_trend_growth_2027_2030 = C.PLAN_DC_2030_GW - C.PLAN_DC_PEAK_TOTAL_GW[2027]            # 1.0 GW
rows = [("Plan (11th Basic Plan)", 0.0, "Plan p.23: total DC summer peak 3.3 GW in 2030"),
        ("GPU programme (treated as fully additional)", GPU_MEDIAN,
         f"Monte Carlo median; P5-P95 {GPU_P5:.2f}-{GPU_P95:.2f} GW; "
         f"{GPU_MEDIAN / plan_trend_growth_2027_2030:.2f} of the Plan's 2027-2030 trend growth"),
        ("Stress 1", 3.7, "total 7.0 GW: above the Plan's own 2038 DC peak (6.2 GW) plus the GPU programme"),
        ("Stress 2", 6.7, "total 10.0 GW"),
        ("Plan reserve-decomposition headroom", 8.49, "DC excess at which the installed reserve falls to 13.1 % (p.43)"),
        ("Stress 3", 11.7, "total 15.0 GW")]
out = []
for name, x, basis in rows:
    out.append({"scenario": name, "dc_excess_peak_GW": x, "dc_total_peak_2030_GW": C.PLAN_DC_2030_GW + x,
                "multiple_of_plan_2038_dc_peak": (C.PLAN_DC_2030_GW + x) / C.PLAN_DC_PEAK_TOTAL_GW[2038],
                "contracted_GW_at_plan_ratio_incr": x / r_incr, "contracted_GW_at_plan_ratio_total": x / r_total,
                "contracted_GW_at_0.7": x / R_AI,
                "multiple_of_plan_suppliable_contracts_to_2027": x / r_incr / supp27, "basis": basis})
df = pd.DataFrame(out)
df.round(3).to_csv(os.path.join(OUT, "dc_scenarios_units.csv"), index=False, encoding="utf-8-sig")
notes = pd.DataFrame([
    {"item": "Plan ratio, peak increment / suppliable contracted capacity, 2027", "value": r_incr},
    {"item": "Plan ratio, total DC peak growth 2023-2027 / suppliable contracted capacity", "value": r_total},
    {"item": "AI facility utilisation bound (assumption)", "value": R_AI},
    {"item": "Plan 2030 DC trajectory as contracts in service (GW), total growth since 2023 / total ratio",
     "value": plan_contracts_2030_total},
    {"item": "Plan 2030 DC trajectory as contracts in service (GW), increment over trend / increment ratio",
     "value": plan_contracts_2030_incr},
    {"item": "Plan DC trend growth 2027-2030 (GW of summer peak)", "value": plan_trend_growth_2027_2030},
    {"item": "GPU programme median / Plan 2027-2030 trend growth", "value": GPU_MEDIAN / plan_trend_growth_2027_2030},
    {"item": "IDC Korea 2025 total DC power / Plan 2025 DC summer peak", "value": idc_ratio_2025},
    {"item": "Plan 2030 DC energy (TWh) as average GW", "value": C.PLAN_DC_ENERGY_TOTAL_TWH[2030] / 8.76},
    {"item": "Plan 2030 DC summer peak / average power", "value": C.PLAN_DC_2030_GW / (C.PLAN_DC_ENERGY_TOTAL_TWH[2030] / 8.76)},
])
notes.round(3).to_csv(os.path.join(OUT, "dc_scenarios_conversion_notes.csv"), index=False, encoding="utf-8-sig")
pd.set_option("display.width", 250)
print(df.round(2).to_string(index=False))
print(notes.round(3).to_string(index=False))
