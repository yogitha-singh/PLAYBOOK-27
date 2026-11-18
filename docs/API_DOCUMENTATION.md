# API (v1) — base `/api/v1`, JSON, uniform errors `{"error":{"code","message"}}`. 25 route-method combinations (verified over HTTP: docs/VERIFICATION.md).
Auth: writes and `/admin/status` need header `X-API-Key` (HTTP 401; 503 if no key is configured in production). Rate limit per IP (429). Only derived aggregates are served.
| Method | Path | Notes |
|---|---|---|
| GET | /health, /health/ready | liveness; DB + outputs readiness (503 if degraded) |
| GET | /overview | counts, top batter/bowler, model status, coverage, recent audit activity |
| GET | /batters/rankings, /bowlers/rankings | status=ranked\|low_confidence\|all, tier=A\|B\|C, role_inferred, q, sort_by(rank,PRI,level100,consistency_pct,pressure_deliveries,p_top10,share_top10,sample_confidence,player,delta100), order, page, page_size≤200 |
| GET | /players?q= · /players/{id}?role= · /players/{id}/explain?role= | detail with risk flags; PRI decomposition (components sum to PRI), shrinkage and uncertainty (ranked players only, else 409) |
| GET | /players/compare?role=&ids=a,b,… | 2–6 players |
| GET | /pressure/overview, /pressure/distribution | definition, thresholds, category validity, by-over and phase mix |
| GET | /models/metrics, /models/feature-importance?task= | all stored metrics, calibration, imbalance comparison; permutation importance |
| GET | /methodology/validation | reliability parameters, split-half, temporal, data validation, cleaning log |
| GET | /scenario/presets, /scenario/simulate | params: innings(1\|2), balls_remaining, wickets_remaining, runs_required (inn 2) or score (inn 1), first_innings_total, tier, striker_order, striker_balls_faced, explain=1. Sections: model_estimates / historical_observations / player_evidence / local_explanation, each labelled |
| GET | /scouting/recommendations?role=&like=&role_inferred=&limit= | alternatives; shortlisted players excluded |
| GET/POST | /scouting/shortlist | POST {player_id, role, note} (key) → 201 / 409 |
| PATCH/DELETE | /scouting/shortlist/{id}?role= | note update / removal (key) |
| GET | /exports/rankings/{bat\|bowl}.csv, /exports/shortlist.csv, /scouting/report/{role}/{id}.pdf | aggregates only |
| GET | /admin/status | key required: manifest, validation summary, migrations, audit count |
