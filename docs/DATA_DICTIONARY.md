# DATA_DICTIONARY (Phase 1)
Raw (confidential; never committed): `ball_by_ball.csv` 200,999 rows × 30 cols (match_id, innings 1-4, overid 1-20, over_ball_num, innings_ball_num [counts illegal balls], batting/bowling_team_id,
striker/non_striker/bowler ids+names, batting_order, batting_type, bowling_type, pace_or_spin, runs [bat only], is_four, is_six, is_wicket, dismissal_type, dismissed_player_id, extras_type
[wide, legbyes, byes, Overstep, other, Penalty], extras1_runs, extras_2_runs, outcome-descriptor columns [excluded as leaky]); `matches.csv` 883; `competitions.csv`; `teams.csv`; `playing_eleven.csv`;
`competition_team_player_mapping.csv`. Keys: match_id, comp_id, team_id, player_id. Duplicate `__*` files are macOS metadata and ignored.
Derived (data/processed, aggregates only — no delivery-level rows): `rankings_{batters,bowlers}.csv` (one row per player with pressure balls: pressure_balls, level100 [runs above expected /100 pressure balls, shrunk],
level_sd100, delta100, consistency_pct, PRI [higher=better], PRI_lo/hi [90% bootstrap], rank, rank_lo/hi, p_top10, p_top20, share_top10/20 [sensitivity grid], tier, status, sample_confidence, role_inferred, conventional and
pressure/baseline stats, strengths/risks/situations text), `final_top20_*.csv`, `sensitivity_*.csv`, `split_half_*.csv`, `temporal_validity_*.json`, `pressure_validity.csv`, `pressure_phase_mix.csv`, `pressure_by_over.csv`,
`pressure_thresholds.json`, `wicket_cost.json`, `reliability_parameters.json`, `model_metrics.json`, `validation_report.json`, `cleaning_log.json`, `dataset_manifest.json` (SHA-256 of raw files, versions, timestamps).

Units: `pressure_deliveries` (statistical n; batters = balls faced, bowlers = all deliveries incl. wides/no-balls), `pressure_legal_balls` (cricket balls). Scenario tables: `scenario_chase_states.csv`/`scenario_setting_states.csv` (state-bin win counts; cells with <5 match-visits suppressed), `scenario_player_bins_*.csv` (player × innings × phase × High/Critical; ≥15 deliveries), `scenario_league_bins.csv`, `feature_medians.json` (ablation background).
