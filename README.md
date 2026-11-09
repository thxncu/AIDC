# Replication package: "Beyond Megawatts: Assessing Grid Adequacy Under Rapid AI Data Center Growth in Korea"

This package contains the input data and the code that produce every table and figure of the article (Tables 1–6, Figs. 1–4) and of its Supplementary Material (Sections S1–S3, Supplementary Tables S1–S6).

## Data

| Input | Source | How to obtain |
| --- | --- | --- |
| KPX 5-minute national supply and demand, 2023–2025 | KPX, "5분단위 전국 전력수급현황" ([data.go.kr 15099819](https://www.data.go.kr/data/15099819/fileData.do)) | Download from https://openapi.kpx.or.kr/sukub.do in 3-month files (the portal's limit). 12 CSV files, EUC-KR, 8 columns. |
| KPX 5-minute national supply and demand, June–September 2026 (out-of-sample) | Same KPX dataset | One file, `2026.6-9.csv`, same format. Used only by `code/run_oos_2026.py`. |
| KPX hourly regional solar and wind trading, 2024 and 2025 | KPX, "지역별 시간별 태양광 및 풍력 발전량" ([data.go.kr 15065269](https://www.data.go.kr/data/15065269/fileData.do)) | One CSV per year (CP949). The portal currently serves the 2025 release; the 2024 file is the previous annual release of the same dataset. Both files are in `data/re_hourly`. |
| Plan values | 11th Basic Plan for Electricity Supply and Demand (MOTIE Notice 2025-169), pp. 22–23, 43, 50, 51, 102 | Constants in `code/config.py` and at the top of the LOLE scripts, each with its page. |
| KPX supply-emergency stages | KPX, "비상시 절전참여요령" ([new.kpx.or.kr](https://new.kpx.or.kr/menu.es?mid=a10606050000)): 준비 < 5.5 GW, 관심 < 4.5, 주의 < 3.5, 경계 < 2.5, 심각 < 1.5 GW of reserve | Constant `KPX_EMERGENCY_STAGES_GW` in `code/config.py` (accessed 7 Nov 2026). |
| GPU and facility parameters | Table 2 of the article | Distributions in `draw()` in `code/run_all.py`. |
| Planning timeline events (Fig. 1b) | Sources in the note to Fig. 1 | Dates and labels in `code/make_figures.py`. |

### Licence

The KPX files are free to use without restriction (data.go.kr licence field "이용허락범위 제한 없음"). They are included in `data/`.

### Layout of `data/`

- `data/kpx_5min_2023_2025/`: the 12 quarterly 5-minute files, 2023–2025 (`2023.1-3.csv` to `2025.10-12.csv`)
- `data/kpx_5min_2026/`: `2026.6-9.csv`, June–September 2026 (out-of-sample)
- `data/re_hourly/`: `re_2024.csv`, `re_2025.csv`

### Data notes

KPX 5-minute data:

- The 2023–2025 files hold 314,563 rows. 3 rows with supply capacity = 0 (2023-05-12 14:05–14:15) are dropped, which leaves 314,560 observations. 1,087 five-minute intervals (0.34 %) are missing; the longest gap starts at 2023-07-01 21:25 and covers 319 intervals.
- The June–September 2026 file holds 35,113 rows. 23 intervals are missing, the longest gap being 8 intervals.
- KPX demand (현재수요) and supply capacity (공급능력) cover the electricity market. The Plan's system-basis targets add solar sold to KEPCO under power purchase agreements (Plan pp. 7, 30–31). KPX's provisional total-demand estimate adds behind-the-meter solar as well, so it matches neither basis and is not compared with the Plan. Every comparison of a Plan demand with KPX data uses the Plan's market-basis targets (`PLAN_MARKET_TARGET_DEMAND_GW` in `code/config.py`).
- KPX's published supply reserve equals supply − (demand + δ). δ was 0–1.5 GW before July 2024 (largest at night) and zero afterwards. At summer peak hours (16–18 h) δ averages 47 MW in 2023, so it does not affect peak-hour results.

KPX renewable trading data:

- The series are traded energy of market generators, not physical generation, and the portal metadata state that solar and wind values include the charging and discharging of storage linked to the plants ("태양광, 풍력 발전량은 ESS 충방전량이 포함되어 있는 수치"). In most mainland provinces the solar series include the evening discharge of PV-linked storage. In 전라남도, 9–10 % of winter solar trading falls after 18:00, after sunset. The base case therefore uses the mainland region with an after-dark winter share ≤ 2 % and ≥ 100 GWh a year, which the code selects by rule (부산시, 1.8–2.0 %). 전라남도, 울산시 and 제주도 are run as sensitivities (`re_solar_after_dark_by_region.csv`).
- Jeju wind trading falls sharply from June 2024 (5–13 GWh a month in June–September, against 24–67 GWh in January–May) and to near zero from March 2025 (1–3 GWh a month; 76 GWh in 2025 against 370 GWh in 2024). The Jeju series is therefore used only to calibrate a wind-variability factor on January–May 2024 (×1.75, matching Jeju's coefficient of variation).
- Each profile is divided by its annual maximum hourly output, so "S GW" of solar or wind means S GW of peak hourly output, not nameplate capacity.

## Requirements

Python 3 with the packages in `requirements.txt` (pandas, numpy, scipy, matplotlib). The outputs in `results/` and `figures/` were produced with Python 3.13, pandas 3.0.5, numpy 2.5.3, scipy 1.18.1 and matplotlib 3.11.2. The figures use the Inter font; without it, matplotlib falls back to its default font.

## Run

From the package root, in this order:

```
pip install -r requirements.txt
python code/run_all.py    data/kpx_5min_2023_2025 results
python code/run_re_ess.py data/kpx_5min_2023_2025 data/re_hourly results
python code/run_lole.py   data/kpx_5min_2023_2025 results
python code/run_lole_sensitivity.py data/kpx_5min_2023_2025 data/re_hourly results
python code/run_oos_2026.py data/kpx_5min_2023_2025 data/kpx_5min_2026 results
python code/run_dc_scenarios.py results
python code/make_figures.py results figures
```

`make_figures.py` reads the outputs of the other scripts, so it runs last. The seven scripts take under a minute in total.

The run is deterministic: the Monte Carlo draws use a fixed seed (`MC_SEED` in `code/config.py`). A second run reproduces every CSV, JSON and PNG output byte for byte; the PDF figures differ only in their embedded creation date. Most outputs are stored with three decimals (the LOLE outputs with four or five), so that the one-decimal values in the article can be checked without double rounding.

## Outputs (`results/`)

| File | Content | Used in |
| --- | --- | --- |
| `dc_scenarios_units.csv`, `dc_scenarios_conversion_notes.csv` | DC scenarios in the Plan's unit (contribution to the summer peak), with the contracted capacity each implies at the Plan's own peak-to-contract ratio (pp. 22–23), the contracts that the Plan's 2030 trajectory already implies (7.2–7.5 GW), and the GPU program as a share of the Plan's 2027–2030 trend growth. The GPU values are read from `monte_carlo_gpu_increment.csv` | Table 3; Sections 3.3, 4.1 and 5.1 |
| `monte_carlo_gpu_increment.csv` | Eq. (2) under the Table 2 specification, realization 50–100 %, independent and correlated inputs, and a variant with IT equipment outside the servers (×1.14, Epoch AI) | Section 4.1; Tables 3 and 4 (GPU program) |
| `monte_carlo_tornado.csv` | Change in the Eq. (2) median when each input moves between its 5th and 95th percentiles | Section 4.1 |
| `monte_carlo_draws_independent.csv` | The 10,000 Monte Carlo draws (Table 2 specification, full realization) | Fig. 1a |
| `headroom_plan_decomposition.csv`, `headroom_scenarios.csv` | DC headroom against the Plan's own reserve decomposition (p. 43); installed reserve at the stress levels | Table 4; Fig. 2a; Section 4.2 |
| `lole_scenario_points.csv` | Exact LOLE, LOLH and EUE at the Table 4 points, both calibrations | Table 4 |
| `lole_dc_excess_sweep.csv` | LOLE, LOLH and EUE for 0–12 GW of unplanned DC load | Fig. 2b |
| `lole_threshold.csv` | DC load at which LOLE reaches 0.3 day/yr | Section 4.2 |
| `lole_fleet.csv` | 2030 summer fleet used in the capacity outage probability table | Supplementary Table S1 |
| `lole_calibration.csv` | The two calibrations to the Plan's LOLE 0.3 day/yr at 13.1 % reserve, with the implied mean availability | Section 3.4; Supplementary Section S1.1 |
| `lole_copt_mc_check.csv` | The capacity outage table checked against 400,000 Monte Carlo draws of unit outages | Section 3.4; Supplementary Section S1.1 |
| `lole_sensitivity.csv` | Re-calibrated variants (unit sizes, outage-rate mix, single load years, hourly variable RE); common-mode nuclear outages of 3 or 6 GW for 219 days recurring every 5, 10 or 20 years (base calibration); the same structural variants with the base calibration constants held fixed; LOLE at the calibration peak for each | Supplementary Table S2; Sections 4.2 and 4.5 |
| `lole_dc_profiles.csv` | LOLE threshold and LOLE/EUE at the stress levels with DC load flat, inference-type diurnal, or following system load (same annual energy) | Supplementary Table S3; Section 4.2 |
| `lole_flexibility.csv` | 15/25/40 % curtailment of the DC excess for 3/4/6 h a day or unlimited, under three operating rules (day's peak hours known + low-load recovery; fixed monthly window + low-load recovery; peak hours known + immediate recovery); firm-capacity equivalent; recovery checks (delivered share of nominal curtailment energy, days with reduced depth or not called, maximum recovery power relative to the limit, maximum delay) | Fig. 4; Sections 3.7 and 4.5 |
| `lole_fixed_windows.csv` | Fixed monthly curtailment window estimated from the 2023–2025 load data (rule b) | Section 3.7 |
| `oos_2026_summer_peak_backcast.csv` | Back-cast of the 83 % rule at the summer peak hour (hourly averages), 2023–2026: ex post, ex ante with the Plan's market-basis targets, ex ante with the system-basis targets (mixed scope, for comparison), KPX published peaks and total-demand estimates, and a load-conditional availability fitted on 2024–2025 hourly daily peaks | Table 5; Section 4.3 |
| `oos_2026_top20_backcast.csv` | The same at the hourly daily peaks of the 20 highest-demand summer days | Table 5 (note) |
| `availability_2023_2026.csv` | Top-20-summer-day and July–August availability on the Plan's summer denominators, 2023–2026, and the top-20-day mean on denominators net of the Plan's system–market target gap | Supplementary Table S4; Section 4.2 |
| `oos_peak_timing.csv` | Peak hour of the 20 highest-demand summer days, 2023–2026 | Section 4.3 |
| `oos_min_reserve_emergency_stages.csv` | Lowest supply reserve of each summer and hours below the KPX emergency stages | Section 4.3 |
| `oos_peak_duration_top20.csv` | Length of peak windows (97 % and 95 % of the daily peak) on the 20 highest-demand summer days, 2023–2026 | Section 4.5 |
| `oos_2026_log.json` | 2026 data QC, load-conditional fit, and the back-cast and availability tables in JSON | Section 4.3 |
| `peak_multiday_events.csv` | Runs of consecutive days at or above 95 % of the annual peak, 2023–2025 | Section 4.5 |
| `peak_duration_top20_days.csv` | Length of peak windows on the 20 highest-demand days of each calendar year, 2023–2025 | Supporting |
| `intraday_reserve_table.csv` | Intraday-minimum and simple-ratio reserve margins, 2030: market-basis target (105.2 GW) with 135.6 GW at 75–90 % availability, and system-basis target (111.4 GW) with 136.7 or 135.6 GW at 90 and 83 %, with time of minimum | Supplementary Table S5; Supplementary Section S2.2 |
| `operational_lens_emergency_stages.csv` | 2030 available supply and reserve at the Plan's market-basis target, at 83 % and at the 2024 and 2025 calendar-year top-20-day availability (Plan summer denominators), against the KPX emergency stages | Supporting |
| `oos_2030_reserve_at_observed_availability.csv` | 2030 reserve at the Plan's market-basis target demand, with 0–11.7 GW of DC excess, when the 2024–2026 top-20-day availabilities of Supplementary Table S4 are applied to 135.6 GW, and the deepest KPX stage reached | Supplementary Section S2.2 |
| `availability_by_load_quintile.csv` | Summer daily-peak availability by load quintile, 2023–2025 (interpolated year-end denominators) | Supplementary Section S2.1 |
| `availability_2023_2025_by_denominator.csv` | Top-20-day (calendar year) and July–August availability, 2023–2025, with the interpolated year-end denominators and the Plan's p. 50 summer denominators | Supporting |
| `backcast_annual_peak.csv`, `backcast_top20_days.csv` | Back-cast of the 83 % rule at each calendar year's five-minute peak and on its 20 highest-demand days, 2023–2025, with both denominators (ex ante with the market-basis targets) | Supporting |
| `run_log.json` | Data QC summary, time of the intraday minimum, peak-window summaries, availability–load regression and Monte Carlo point estimate | Section 3.1; Supplementary Sections S2.1 and S2.2 |
| `re_ess_grid.csv` | 24 RE × ESS configurations, 2024 and 2025: self-supply, grid energy, grid draw in the 100 highest-load and 100 lowest-reserve hours, longest grid-draw run, curtailment | Table 6; Section 4.4 |
| `re_ess_sensitivity.csv` | Solar region, Jeju-calibrated wind variability, solar-only, alternative conventions | Supplementary Table S6; Section 4.4 |
| `re_ess_hourly_<year>_S5W2.5_E8.csv` | Hourly KPX electricity-market load and supply reserve, RE, ESS and grid draw for 5 GW solar + 2.5 GW wind + 8 GWh storage | Fig. 3 |
| `re_solar_after_dark_by_region.csv`, `re_profile_stats.csv`, `re_settings.csv` | Profile checks and the settings chosen by rule | Section 3.6; Supplementary Section S3.2 |

Figures (`figures/`, PDF and 600-dpi PNG):

| File | Used in |
| --- | --- |
| `fig_mc_timeline` | Fig. 1, GPU program estimate and planning timeline |
| `fig_adequacy_headroom` | Fig. 2, headroom and calibrated adequacy of the 2030 system |
| `fig_residual_timing` | Fig. 3, timing of residual grid draw relative to KPX electricity-market load |
| `fig_flex_duration` | Fig. 4, firm-capacity value of DC flexibility by curtailment duration |
| `fig_backcast` | Supporting plot of the back-cast (values in Table 5) |

Table 1 (data sources) and Table 2 (Monte Carlo parameters) describe inputs and have no output file.

## Method notes

### Monte Carlo (`code/run_all.py`)

Eq. (2) is evaluated for 10,000 draws under the Table 2 specification. The median is 361 MW (5th–95th percentile 234–541 MW). Eq. (2) multiplies the GPU count by the maximum power per GPU (P_max), the server overhead factor, the peak power factor U (the assumed share of maximum power drawn at the system peak) and PUE. A Gaussian-copula variant sets ρ = −0.4 between GPU power and PUE and ρ = −0.3 between the peak power factor and PUE. The tornado moves each input between its 5th and 95th percentiles with the others at their medians. Including IT equipment outside the servers, mainly networking (about 14 % of server power at peak operation, Epoch AI), multiplies every draw by 1.14 and gives a median of 412 MW (267–617 MW). It covers Eq. (2) only, because non-AI DC growth is not part of Eq. (2).

### Probabilistic adequacy (`code/run_lole.py`)

The Plan does not publish its RASMO inputs, so the model is calibrated to the Plan's own statement (p. 43) that a 13.1 % installed reserve meets LOLE 0.3 day/yr in 2030:

1. The fleet is the Plan's 2030 effective capacity by source, scaled to the 124.1 GW summer conventional total, with renewables as an 11.5 GW firm block. Unit sizes and base forced-outage rates are representative assumptions.
2. Load uses KPX hourly demand for 2023, 2024 and 2025, each scaled to the tested peak. LOLE (days/yr) uses daily peaks; LOLH and EUE use all hours. Results are averaged over the three load years.
3. Two calibrations represent two plausible structures for the unknown inputs. *Outage scaling* multiplies all forced-outage rates by 2.88. *Derate* adds a 9.75 GW unavailable block to the base rates. Both give LOLE = 0.3 day/yr when the 135.6 GW fleet serves 119.9 GW.
4. The capacity table is checked against 400,000 Monte Carlo draws of unit outages. Loss-of-load probability and expected unserved power agree within sampling error (e.g., 0.1277 vs 0.1281 at 119.9 GW, standard error 0.0005).

The calibrated models imply a mean available capacity of 89.6–90.7 % of summer effective capacity. KPX's observed top-20-summer-day availability on the same denominators is 82.3–83.4 % (2024–2026).

The DC excess at which LOLE = 0.3 day/yr (8.4 GW) is close to the Plan-decomposition value (8.49 GW) by construction, because both rest on the same 13.1 %. It is a consistency check of the construction. The COPT–Monte Carlo comparison checks the numerical implementation under the same unit assumptions.

### Robustness (`code/run_lole_sensitivity.py`)

The script implements the same model separately from `run_lole.py`; its base case matches `run_lole.py` to four decimals. It runs three groups of variants.

1. Re-calibrated: larger or smaller units, a uniform 4 % outage rate, each load year alone, the 2024–2025 load years alone, and hourly variable RE instead of a firm block. Each reproduces LOLE 0.3 day/yr at the calibration peak, so the narrow range of thresholds (8.26–8.46 GW) reflects the common anchor.
2. Common-mode nuclear outages, added to the base calibration because the Plan's standard is taken not to cover them. They follow the 2013 precedent: the Nuclear Safety and Security Commission found safety-grade control cables with forged test certificates at Shin-Kori 1–2 and Shin-Wolsong 1–2 and ordered Shin-Kori 2 and Shin-Wolsong 1 shut down and the Shin-Kori 1 outage extended (press release, 28 May 2013); it approved restart of the three units on 2 Jan 2014, 219 days later (press release, 2 Jan 2014). The cases take 3 GW (the three 1-GW-class units) or 6 GW unavailable for 219 days. The precedent gives the size and duration of an event, not its frequency, so the recurrence interval is varied: once every 5, 10 or 20 years (12.0 %, 6.0 % or 3.0 % of days). With 6 GW, the LOLE 0.3 threshold is 5.46–5.95, 6.68–6.96 and 7.54–7.62 GW.
3. Fixed calibration: the unit-size, outage-rate-mix and single-load-year variants with the base calibration constants (multiplier 2.88 or derate 9.75 GW) held fixed; the hourly variable-RE variant is not part of this group. They no longer reproduce the Plan's anchor (LOLE at the calibration peak 0.15–0.99 day/yr), and the threshold moves to 6.18–9.27 GW (8.08–8.80 GW across load years).

The value of 3-hour flexibility is the least robust output: at +11.7 GW under rule (a), it falls from 60 % to 29–30 % of nominal for the 2024–2025 load years when RE enters hour by hour.

Sources for the common-mode precedent (both NSSC press releases, republished on the government briefing portal):

- NSSC, 28 May 2013, "신고리 1·2호기, 신월성 1·2호기에 설치된 안전등급 제어케이블의 시험성적서 위조 확인", https://www.korea.kr/briefing/pressReleaseView.do?newsId=155897674
- NSSC, 2 Jan 2014, "원자력안전위원회, 신고리 1·2, 신월성 1호기 재가동 승인", https://www.korea.kr/briefing/pressReleaseView.do?newsId=155936997

### Storage dispatch (`code/run_re_ess.py`)

The dispatch equations are in the docstring of `code/run_re_ess.py`. Every run checks the hourly energy balance and the SOC identity. The base case uses η_c = η_d = √0.9 and a warm start. The alternative conventions of Supplementary Table S6 use 전라남도 solar, apply the 90 % round-trip loss on discharge only and start from an empty store.

### Construction of Supplementary Table S5 (`code/run_all.py`)

1. Take the 5-minute demand and supply-capacity curves of the 2025 peak day (25 Aug 2025).
2. Scale demand so its daily maximum equals a 2030 target demand: the market-basis target (105,200 MW, p. 31), which matches the scope of KPX data and of the availability ratio, or the system-basis target (111,383 MW, p. 30) for comparison.
3. Normalise supply capacity to 1 at the moment of peak demand and multiply by effective capacity × availability.
4. Add the DC excess as a flat load and report the minimum of (supply − demand)/demand over the 288 intervals.

With the market-basis target the table uses the Plan's summer effective capacity (135.6 GW, p. 50); with the system-basis target it uses 136.7 GW (year-end, p. 51) and 135.6 GW. The minimum falls at 18:45, about an hour after the demand peak. By then supply capacity has fallen to 98.1 % of its peak-moment value, while demand is still at 98.4 %. For this reason Supplementary Table S5 sits 0.3–0.5 pp below the simple ratio (a·S − D)/D, where a is the availability ratio.

### Flexibility recovery (`code/flex.py`)

Both LOLE scripts use `apply_flex()` in `code/flex.py`. Each day, a share f of the DC excess x is curtailed in the day's curtailment hours, and the deferred work is recovered under three constraints that the code checks with assertions on every run:

1. Power: recovery adds at most f·x·H/6 in any hour, the spare capacity needed to recover a full day's deferral in six hours (7.5–40 % of the DC excess across the cases).
2. Timing: recovery hours come after the day's last curtailed hour, before the next day's first curtailed hour, and no later than 24 hours after the day's first curtailed hour, so every deferred job finishes within 24 hours of its own curtailment and no backlog carries over.
3. Energy: all curtailed energy is recovered.

Rules (a) and (b) use the six lowest-load eligible hours (low-load recovery); rule (c) uses the first six eligible hours (immediate recovery). When only m < 6 eligible hours exist, the day's curtailment depth is scaled by m/6, and with m = 0 the day is not called. Averaged over the 2023–2025 load years, this happens on 11–43 days a year under rules (a) and (c) (3–6 h; 7–47 days in single years), on 1–5 days in June–September over the three years and on none of the 20 highest-demand summer days of any year. Across the operating rules and durations, mean delivered curtailment energy is 94–100 % of nominal (93–100 % in single years). The firm-capacity equivalent is still expressed as a share of the nominal curtailment f·x.

### Denominators

Availability is KPX supply capacity divided by the Plan's summer effective capacity of the same year (p. 50: 121.7, 125.5 and 128.7 GW for 2024–2026). The Plan's summer table starts in 2024, so 2023 uses an interpolated value of 120.7 GW. The interpolated year-end denominators for 2023–2025 (120.7, 123.8 and 126.9 GW, `INTERP_EFFCAP_GW` in `code/config.py`) are also used as an alternative denominator in the supporting availability and back-cast files and in the availability–load regression.
