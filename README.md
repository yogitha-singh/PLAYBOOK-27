# PLAYBOOK 27 — THE SCIENCE BEHIND THE SELECTION.
Pressure-performance analytics for the Rajasthan Royals SupeRR Selector (Season 2, Round 1): *who performs better than expected when the match situation gets difficult, and how sure are we?*

## Status (honest)
| Area | State |
|---|---|
| Data pipeline, pressure framework, models, reliability index, uncertainty/stability, rankings | **Done, tested** (Phase 1) |
| Backend API (25 route-methods), SQLite + migrations, auth, rate limit, PDF/CSV exports, scenario simulator | **Done, tested** — `docs/VERIFICATION.md` (45 checks over real HTTP) |
| Frontend (10 modules, design system, logo, SVG charts, scenario simulator) | **Built; render logic tested against the live API (21 Node tests). Never opened in a browser** — layout, responsiveness, dialog/keyboard behaviour and all event wiring are unverified (`docs/FRONTEND.md`) |
| Deployment | **Not deployed. No URL.** Docker/CI files written, **not executed** (see `docs/DEPLOYMENT.md`) |

**Read this first:** a split-half and out-of-time validation found pressure-specific performance is only *weakly persistent* (split-half ≈0.29 batters / 0.24 bowlers after correction; out-of-time mixed). Rankings are evidence with wide intervals, not a precise order — use tiers (A/B/C), intervals, P(top-10) and sensitivity shares. The "clutch delta" (pressure vs own baseline) showed no detectable signal and carries zero weight. See `docs/METHODOLOGY.md` §7.

## Method in brief
Pressure = top 20% of a model-based **Leverage Index** (expected win-probability swing of the next ball) *within each innings*. Performance = value above the expectation of an *average player in the same situation* (cross-fitted, player-agnostic models). **PRI** = empirical-Bayes-shrunk level + delta + consistency (each in units of its estimated true SD; equal weights). Eligibility is data-derived (≥128 batter / ≥126 bowler pressure deliveries). Uncertainty: match-bootstrap intervals, P(top-10), a 255-configuration sensitivity grid, tiers. Details, formulas, decisions and limitations: `docs/METHODOLOGY.md`.

## Setup & run
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env                       # set PLAYBOOK_API_KEY for production
PLAYBOOK_RAW_DIR=/path/to/data_pack python scripts/run_pipeline.py     # ~3 min -> data/processed/, models/
cd backend && PLAYBOOK_ENV=development python -m flask --app wsgi run  # http://127.0.0.1:5000  (UI: /  ·  API: /api/v1)
```
`--reuse-expectations` re-runs only the evaluation stage (~15 s) from the cached, gitignored interim dataset; `--boot N` sets bootstrap replicates. **Retraining experiments:** edit `analytics/config.py` (split dates, folds, pressure cuts, eligibility) and `ml/models.py` (grids), rerun the pipeline; a clean rerun reproduces identical outputs (seed 27).

## Tests
`cd backend && python -m unittest discover -s tests -t . -v` — 59 tests (+ `cd frontend && node --test tests/*.test.js` — 21 tests, needs Node ≥ 20): cricket scoring rules, leakage guard, statistics (shrinkage properties), output integrity & unit consistency, doc↔metric consistency, API (auth, validation, errors, rate limit, injection), scenario simulator, SQLite migrations, strict-JSON responses, frontend↔backend route contract. `python scripts/verify_backend.py` runs the live-HTTP verification and regenerates `docs/VERIFICATION.md`.

## Documentation
`docs/METHODOLOGY.md` · `FRONTEND.md` · `MODEL_CARD.md` · `DATA_DICTIONARY.md` · `ARCHITECTURE.md` (incl. **technology substitutions**) · `API_DOCUMENTATION.md` · `DEPLOYMENT.md` · `VERIFICATION.md`.

## Confidentiality
The raw data pack is competition-proprietary: keep it outside git (`data/raw/`, `data/interim/` and the pack's file names are ignored). Only player-level aggregates and small-cell-suppressed scenario tables are served; no delivery-level rows are in `data/processed/` (a test enforces this).

## Known limitations
Roles are inferred, not verified; team labels are "latest team in data"; auction availability, prices, injuries are not in the data and are never claimed. IPL and T20I deliveries are pooled with tier/Elo controls. Wicket cost differs by innings (25.7 vs 5.5 runs; sensitivity-tested ×0.5/×2). Ball-level models are modest (R²≈0.035, AUC≈0.60). No clustering, SHAP or full Bayesian intervals (reasons in methodology §9). Single-process rate limiting; SQLite single-writer.
