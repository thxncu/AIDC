"""Constants used by the replication scripts, with their sources.

Plan = 11th Basic Plan for Electricity Supply and Demand (MOTIE Notice No. 2025-169,
21 Feb 2025). Page numbers refer to the published PDF.
"""

# ---------------------------------------------------------------- Plan values
# Summer supply-demand balance table (Plan p.50): target demand and confirmed
# summer effective capacity (GW). These are the values the Plan uses for its
# installed reserve margin.
PLAN_TARGET_DEMAND_GW = {2024: 101.0, 2025: 102.5, 2026: 104.2, 2027: 106.2,
                         2028: 107.8, 2029: 109.3, 2030: 111.4}
PLAN_SUMMER_EFFCAP_GW = {2024: 121.7, 2025: 125.5, 2026: 128.7, 2027: 132.1,
                         2028: 133.5, 2029: 134.5, 2030: 135.6}

# Market-basis target demand (Plan p.31, summer peak, GW). The Plan separates system demand
# (p.30, above) from market demand because solar outside the electricity market is not metered
# (Plan p.31, 참고 8); system demand = market demand + solar sold to KEPCO under power purchase
# agreements (Plan p.7). KPX demand and supply capacity are market-basis, so every comparison of
# a Plan demand with KPX observations uses these values. KPX's provisional total-demand estimate
# also adds behind-the-meter solar and matches neither basis. The Plan's reserve margin and
# reserve standard use the system basis (p.43, p.50).
PLAN_MARKET_TARGET_DEMAND_GW = {2024: 95.6, 2025: 96.8, 2026: 98.1, 2030: 105.2}

# KPX published hourly-average summer peaks (market basis, MW) and KPX's provisional estimate of
# total demand at the same hour (market + KEPCO PPA solar + behind-the-meter solar; recorded for
# reference only), from KPX "최근 5년간 최대전력 실적"
# (https://www.kpx.or.kr/powerinfo5years.es?mid=a30103000000, accessed 9 Nov 2026).
KPX_PUBLISHED_SUMMER_PEAK_MW = {2023: 93615, 2024: 97115, 2025: 95951}
KPX_TOTAL_DEMAND_ESTIMATE_AT_PEAK_MW = {2024: 103591, 2025: 104215}

# The Plan's year-end effective capacity for 2030 (Plan p.51). The intraday
# reserve table (Supplementary Table S5) is reported for this value and for the
# Plan's summer effective capacity above (135.6 GW).
PLAN_YEAREND_EFFCAP_2030_GW = 136.7

# Reserve-margin standard decomposition for 2030 (Plan p.43), in percent of
# target demand: capacity adequacy (LOLE 0.3 day/yr) + demand uncertainty
# + supply uncertainty = 20.1 %. The applied medium-term standard, which covers 2030, is 21 %.
PLAN_RM_2030 = {"capacity_adequacy_LOLE": 13.1, "demand_uncertainty": 6.1,
                "supply_uncertainty": 0.9, "computed_total": 20.1,
                "applied_medium_term": 21.0}

# DC demand in the Plan (p.23): total DC summer peak 3.3 GW in 2030.
PLAN_DC_2030_GW = 3.3
# Plan p.22-23. DC demand = new contracted capacity x utilisation (rate not published).
# To 2027 the Plan counts the 4,718 MW of requests judged suppliable by Aug 2023; from 2028 it
# extends the trend of connection requests, and it adds only the part above the existing
# consumption trend of the demand model (p.23).
# Summer peak (GW): total DC and increment over trend; 2023 = actual (0.6 GW, 5.0 TWh).
PLAN_DC_PEAK_TOTAL_GW = {2023: 0.6, 2025: 1.2, 2027: 2.3, 2030: 3.3, 2036: 5.4, 2038: 6.2}
PLAN_DC_PEAK_INCREMENT_GW = {2025: 0.5, 2027: 1.5, 2030: 2.3, 2036: 3.9, 2038: 4.4}
PLAN_DC_ENERGY_TOTAL_TWH = {2023: 5.0, 2025: 8.2, 2027: 14.8, 2030: 18.0, 2036: 26.4, 2038: 30.0}
# Plan p.22: DC connection requests and capacity judged suppliable (MW, cumulative to each year,
# as of Aug 2023).
PLAN_DC_CONTRACT_REQUESTED_MW = {2023: 906, 2024: 2724, 2025: 4866, 2026: 6531, 2027: 7343}
PLAN_DC_CONTRACT_SUPPLIABLE_MW = {2023: 776, 2024: 2514, 2025: 3738, 2026: 4578, 2027: 4718}
# IDC Korea (2025) forecast of total DC power (facility power, not contribution to peak), MW.
IDC_DC_POWER_MW = {2025: 4461, 2028: 6175}

# ------------------------------------------- denominators and screening inputs
# Interpolated year-end effective capacity, 2023-2025 (GW). The Plan's summer
# table (p.50) starts in 2024, so 2023 has no Plan summer value; its interpolated
# value (120.7 GW) is the 2023 denominator in Table 5 and Supplementary Table S4.
# The full series is the alternative denominator in the 2023-2025 availability
# and back-cast outputs and in the availability-load regression.
INTERP_EFFCAP_GW = {2023: 120.7, 2024: 123.8, 2025: 126.9}
TARGET_DEMAND_2030_MW = 111383             # 2030 system-basis target demand (MW), intraday reserve table
TARGET_DEMAND_2030_MARKET_MW = 105200      # 2030 market-basis target demand (MW, Plan p.31)
INTRADAY_PROFILE_DAY = "2025-08-25"        # 2025 peak day, intraday demand and supply profile
AVAILABILITY_SCENARIOS = [0.90, 0.83, 0.77, 0.75]
DC_EXCESS_GW = [0.0, 3.7, 6.7, 11.7]       # unplanned DC load above the Plan (GW)

# ------------------------------------------------------------ KPX operations
# KPX supply-emergency stages (reserve below which each stage applies, GW).
# Source: KPX, "비상시 절전참여요령" (전력수급비상 단계별 행동요령),
# https://new.kpx.or.kr/menu.es?mid=a10606050000 (accessed 7 Nov 2026; no update date on the page).
# Same thresholds in Korea Energy Agency, Energy Issue Briefing No. 250 (7 Oct 2024).
# KPX states the thresholds as "예비전력" without naming supply or operating reserve; here they
# are compared with available supply minus demand (supply reserve).
KPX_EMERGENCY_STAGES_GW = {"preparation (준비)": 5.5, "attention (관심)": 4.5,
                           "caution (주의)": 3.5, "alert (경계)": 2.5,
                           "serious (심각)": 1.5}

# ------------------------------------------------------------- Monte Carlo
N_GPU = 260_000
MC_SEED = 20261107
MC_N = 10_000
