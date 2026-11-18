# ARCHITECTURE

```
raw CSVs (confidential, outside git)
   │  scripts/run_pipeline.py  (deterministic, seed 27; verified: a full retrain reproduced identical rankings and metrics)
   ▼
analytics/ingest → validate → clean → features → ml/train (cross-fitted context models) → pressure → value → reliability (EB) → stability → engine → scenario
   ▼
data/processed/*.csv|json   (player-level aggregates + small-cell-suppressed scenario tables; NO delivery-level rows)     models/*.joblib (gitignored)
   ▼
Flask app (backend/app): api/routes → services/{rankings,scouting,scenario,reports} → repositories/analytics_repo (read-only files, cached) + database/db (SQLite)
   ▼
frontend/ (Phase 3: static SPA served by the same Flask app)
```
**Hybrid data design.** Analytical results are versioned files (read-only, cached); SQLite holds only application state (shortlist, notes, audit log). Delivery-level data is never loaded
by the application. Migrations are plain SQL files applied by a small runner (`database/db.py`, tested for idempotence/constraints/rollback).
**Layers.** `analytics/` and `ml/` have no web dependencies and run offline; `services/` hold business logic and raise `ApiError`; `api/routes.py` only parses parameters and shapes JSON.
**Cross-cutting.** JSON structured logs with request ids; API-key auth that fails closed; per-IP in-memory rate limiter; CORS allow-list; security headers; uniform error envelope.
**Reproducibility.** `dataset_manifest.json` records SHA-256 of raw files, versions, timestamps; `model_metrics.json` holds every metric; unit tests assert units and doc/metric consistency.

## Technology substitutions (honest list)
| Specified | Used | Why | Consequence |
|---|---|---|---|
| FastAPI + Pydantic | Flask 3 + hand-written validation (`ApiError`) | FastAPI/Pydantic not installable offline; Flask was present | no auto OpenAPI docs; validation is manual (tested) |
| PostgreSQL + SQLAlchemy + Alembic | SQLite (stdlib) + SQL migration runner | not installable / no DB server offline | single-writer; fine for a shortlist workspace, not for multi-instance production |
| XGBoost | scikit-learn HistGradientBoosting | XGBoost unavailable | comparable gradient-boosted trees |
| SHAP | permutation importance + ablation-based local attribution | SHAP unavailable | association only; see METHODOLOGY §9 |
| React + TS + Vite + Tailwind + Recharts | dependency-free HTML/CSS/ES-modules + SVG charts (Phase 3) | npm unavailable offline | no type-checking or component library; see Phase 3 notes |
| pytest | unittest | pytest unavailable | pytest also runs these tests |
| Redis/other caching | in-process caching of read-only files | not needed at this scale | per-process; multi-worker rate limiting is per worker |
