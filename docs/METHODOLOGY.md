# PLAYBOOK 27 — Methodology (Phase 1)

Central question: **who performs better than expected when the match situation becomes difficult — and how sure are we?**
Every number below is produced by `scripts/run_pipeline.py` (seed 27) and stored in `data/processed/`.

## 1. Data and scope
803 of 867 matches with ball data are in scope (IPL 353, T20I 420, A-team events 30; 191,903 deliveries). Excluded and logged in
`cleaning_log.json`: 29 DLS/revised-overs matches, 22 single-innings matches, 13 truncated-innings matches; super-overs (innings 3-4).
Scoreboard-derived winners agree with `win_team_id` in 794/794 decided matches; innings totals reconcile with stated run margins in the
validation suite (`validation_report.json`: 12 PASS, 7 WARN, 0 FAIL; warnings are documented source characteristics, not hidden drops).

Cricket rules: legal ball = not wide/no-ball/penalty; balls faced exclude wides but include no-balls; bowler runs = bat runs + wides + no-ball
penalty (byes/leg-byes/penalty excluded); bowler wickets exclude run-out/retired/obstructing; a batter's dismissal = being dismissed while on strike
(retired-out excluded). Player identity = `player_id`; 3 duplicated names are disambiguated in display.

## 2. Pre-delivery state (no leakage)
Score, wickets, legal balls, balls/wickets remaining, target & required rate (chase), striker's balls/runs so far, batting order, hand, pace/spin,
pre-match Elo (chronological), venue first-innings par (earlier matches only), competition tier. Cumulative quantities are shifted one ball.
`stroke`, `delivery_style`, `bowl_speed`, `on_or_off` etc. describe the outcome and are never inputs (`features.assert_no_leakage`, unit-tested).
`crr`/`rrr_minus_crr` are excluded from the win-probability model because they are unstable in the first balls.

## 3. Pressure = leverage
Win-probability model WP (batting side, per-innings gradient boosting with monotonic constraints) → for each delivery the model-expected
**|change in WP| of the next ball**, `lev_hat`, learned from pre-delivery state only (cross-fitted) → Leverage Index `LI = lev_hat / mean`.
Categories are quantiles of LI **within each innings** (setting vs chasing have structurally different leverage scales; pooled quantiles would
turn "pressure" into "chasing"): Low <P50, Moderate P50–P80, High P80–P95, Critical ≥P95. **Pressure = High + Critical (top 20%).**
LI thresholds: innings 1 P50/P80/P95 = 0.55/0.80/1.20; innings 2 = 1.02/2.04/4.31.

Why it is meaningful (`pressure_validity.csv`, outcomes not used in the definition): from Low to Critical the dismissal rate is 5.2% / 5.1% / 5.7% / 8.9% (flat for Low–Moderate, not strictly monotone, clearly higher in Critical),
wickets in hand fall 7.5→4.9, balls remaining 70→16, dot% falls 39.9→31.3 and run rate rises (1.34→1.63 per ball). It is **not** a death-over
rule: High pressure is 11% powerplay / 55% middle / 34% death; pressure share is already 15–17% of deliveries in overs 5–10 of the chase and 16–24% in overs 10–14 of the first innings (`pressure_by_over.csv`).
Limitation: first-innings pressure is concentrated late and in collapses; match leverage for a team's quality is estimated, not observed.

## 4. Performance relative to expectation
Player-agnostic, match-grouped cross-fitted models give, for every ball, the expected runs/dismissal probability (batting) and expected runs
conceded/wicket probability (bowling) of an *average player in the same situation*. Residual **streams** (positive = better for the player):
batter runs-above-expected and dismissal-avoidance; bowler runs-saved and wickets-above-expected. A wicket is converted to runs with
`V = 15.6` runs (mean of innings-specific OLS ratios of WP effects: 25.7 innings 1, 5.5 innings 2 — a real uncertainty; the grid tests ×0.5 and ×2).

## 5. Pressure Reliability Index (PRI)
Components on pressure balls, each **empirically-Bayes shrunk separately** (normal–normal, DerSimonian–Laird, heteroskedastic):
`LEVEL` (value above expectation per 100 pressure balls), `DELTA` (pressure minus the player's own non-pressure value), `CONSISTENCY`
(share of pressure appearances with ≥6 pressure balls and value ≥0). Streams are shrunk separately *then* combined (`runs + V·wickets`) so noisy
wicket outcomes cannot contaminate the scoring signal. Each shrunk component is expressed in units of its estimated true-score SD τ
(`z = (post − μ)/τ`), so a component with no detectable signal gets zero weight automatically; remaining weights are equal (1:1:1, no invented weights).
`PRI = 50 + 10 × mean(z)`; **higher is better**. Fitted τ: LEVEL 0.077 runs/ball (batters) and 0.076 (bowlers); **DELTA τ = 0** for both —
pressure-vs-own-baseline differences are statistically indistinguishable from luck here, so DELTA is reported descriptively but carries no weight.

Eligibility is data-derived: ≥ `k·B/(1−B)` pressure balls with B = 0.20 (≥20% of the posterior from the player's own data), k = ball-variance/τ²:
**128 balls (batters), 126 (bowlers)**, plus ≥6 pressure appearances → 94 batters and 100 bowlers ranked; 65/74 further players with ≥½ of the minimum are
shown as *Low-confidence* and are never ranked.

## 6. Uncertainty and stability
* 90% intervals and P(top-10)/P(top-20): bootstrap over **matches** (300 reps; EB hyper-parameters held fixed — re-estimating them per replicate was found to bias intervals and was corrected).
* Sensitivity grid (255 configs per role): 6 pressure definitions (primary, pooled quantiles, top-15%, top-30%, Critical-only, rule-based closeness) × wicket cost ×0.5/1/2 × 5 weight sets × 3 minimum samples → `sensitivity_*.csv`.
* Tiers: **A** = rank ≤20 with P(top-10) ≥0.30 and grid share ≥0.30; **B** = rank ≤20, plausible but assumption-sensitive; **C** = ranked pool.

## 7. Independent validation — honest results
| Check | Batters | Bowlers |
|---|---|---|
| Split-half reliability (Spearman–Brown), shrunk LEVEL | 0.29 | 0.24 |
| …CONSISTENCY / composite | 0.09 / 0.19 | 0.18 / 0.18 |
| …DELTA | −0.26 | −0.02 |
| Early→late (cutoff 2025-07-31) Spearman of PRI with later pressure value | −0.37 (n=45) | +0.26 (n=53) |
| Early top-10 later pressure value /100 balls vs pool | −2.8 vs 17.7 | 17.7 vs 5.5 |

**Interpretation:** pressure-specific performance is only weakly persistent in a ~4-year, ~800-match sample; rankings are evidence with wide
uncertainty (bootstrap rank intervals are often 2–40), not a precise order. Out-of-time evidence is mixed (negative for batters, positive for bowlers; small n,
cutoff 2025-03-31 gave batters −0.15 and bowlers no detectable early signal). We therefore report tiers and intervals and recommend the shortlist be used with
role fit and scouting judgement.

## 8. Decisions recorded
* Primary definition was fixed before player names were inspected; later findings (definition-sensitive players) are reported, not used to re-rank.
* A first pressure definition (pooled, unstable rate features) was rejected after validity checks showed 79% of first chase over flagged; replaced as above.
* Model selection uses chronological VALID only; an early draft that compared on TEST was corrected.
* Balanced class weights were rejected: ECE 0.003 → 0.43 with no recall gain.

## 9. Not implemented, and why
* **Player clustering (brief §5.4):** not built. The reliability analysis shows pressure-specific signal is weak (split-half ≈0.2–0.3), so clusters of "pressure performers" would mostly separate noise. Role profiles are shown as *inferred labels* instead.
* **SHAP:** not installable offline. Replaced by permutation importance (global) and ablation-based local attribution (scenario `explain=1`); both describe predictive association, not causation.
* **Full Bayesian credible intervals:** not built. With ~800 correlated matches, a hierarchical model's priors would drive results; we use empirical-Bayes shrinkage (normal–normal) plus a match-level bootstrap. Intervals are therefore approximate and conditional on estimated hyper-parameters (τ² held fixed in the bootstrap).
* **Role-adjusted ranking:** deliberately not added. Review (measurement only): eligible batters are 48% middle-order / 22% finisher / 22% opener / 6% number 3 / 1% lower order and the top-10 is 6/2/2/0/0 — consistent with the pool; mean PRI by role differs by ≤2 points, inside bootstrap noise. Bowlers: spin is 33% of the pool and 6 of the top 10 (hypergeometric P≈0.063, not significant); by overs type mean PRI is 51.0 (death), 50.8 (middle), 49.8 (powerplay). PRI correlates with pressure sample size for bowlers (r=0.27; intended shrinkage effect) and not for batters (r=−0.03). Context models already condition on batting order, over, striker's balls faced, pace/spin; pressure is defined within innings. No role weights were introduced because none can be justified from this data.

## 10. Units (resolved mismatch)
`pressure_deliveries` is the statistical unit used for shrinkage, eligibility and confidence: for batters it equals balls faced; for bowlers it counts **all deliveries bowled including wides/no-balls**. `pressure_legal_balls` is the cricket balls count (bowlers: legal only; among the 357 affected bowlers the mean gap is 5.7 and the maximum 55). Earlier outputs called the first quantity "pressure_balls"; bowler scouting profiles showed legal balls, which produced apparent discrepancies for 357/553 bowlers. No result changed (a full rerun reproduced identical ranks, PRI, intervals, tiers and model metrics); labels now state the unit everywhere and a test enforces consistency.

## 11. Scenario simulator
`/scenario/simulate` returns three separate sections: **model estimates** (win probability, leverage, pressure category, expected next-ball runs/dismissal for an average batter — from the deployed models, with stated default assumptions), **historical observations** (win frequency in pooled neighbouring match-states with Wilson interval, the pooled average state, comparability warnings and an independence caveat), and **player evidence** (recorded outcomes in the same innings × phase × pressure category; cells ≥15 deliveries; only for High/Critical states). History and model output can legitimately differ (e.g. the "12 needed from the final over" preset: model 0.58 vs pooled history ≈0.80, because the pool is one-sided at the innings boundary and averages ~8 balls remaining — flagged in the response). WP calibration check (cross-fitted): chases overall predicted 0.485 vs observed 0.485; last two overs 0.310 vs 0.322; ≤9 balls & 9–16 needed 0.370 vs 0.403 (slightly under-confident for outsiders late). It is not a match predictor.

## 12. Limitations
Roles are **inferred** (median batting position; pace/spin and phase usage), not verified. Team labels are the latest team in the data; auction availability, injuries,
price and overseas slots are **not** in the data and not claimed. IPL and T20I deliveries are pooled with tier and Elo controls; opposition bowler/batter quality is not individually modelled.
Wicket cost V differs by innings. SHAP/XGBoost were unavailable offline: explainability uses permutation importance and ablation-based local attribution (association, not causation).

## 13. References (methods)
Tom Tango, *Leverage Index* (baseball; the concept adapted here); DerSimonian & Laird (1986), random-effects estimator; Efron & Morris (1975), empirical-Bayes shrinkage;
Duckworth–Lewis–Stern resource idea (context only); scikit-learn documentation (HistGradientBoosting, monotonic constraints, permutation importance). No cricket-specific
academic results are cited as validating this index.
