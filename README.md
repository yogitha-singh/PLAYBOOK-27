# PLAYBOOK 27 — THE SCIENCE BEHIND THE SELECTION.

Pressure-performance analytics for the Rajasthan Royals SupeRR Selector (Season 2, Round 1): *who performs better than expected when the match situation gets difficult, and how sure are we?*

## Status
| Area | State |
|---|---|
| Data pipeline, models, reliability index, stability, rankings | **Done, tested** |
| Backend API (25 routes), SQLite, auth, PDF/CSV exports | **Done, tested** |
| Frontend (10 modules, design system, SVG charts) | **Built, integrated** |
| Deployment | **Koyeb (Docker)** |

**Read this first:** pressure-specific performance is only *weakly persistent* (split-half ≈0.29 batters / 0.24 bowlers). Rankings are evidence with wide intervals, not a precise order — use tiers (A/B/C), intervals, P(top-10) and sensitivity shares.

## Method in brief
Pressure = top 20% of a model-based **Leverage Index** within each innings. Performance = value above the expectation of an *average player in the same situation*. **PRI** = empirical-Bayes-shrunk level + delta + consistency.

## Repository Structure
- `backend/` — Flask API, SQLite DB, and the Scikit-learn ML pipeline.
- `frontend/` — Vanilla JS dashboard with SVG charts.
- `data/processed/` — Aggregated rankings and scenario tables.
- `models/` — Trained gradient boosting models.
- `docs/` — Full methodology, architecture, and validation results.

## Documentation
`docs/METHODOLOGY.md` · `FRONTEND.md` · `MODEL_CARD.md` · `DATA_DICTIONARY.md` · `ARCHITECTURE.md` · `API_DOCUMENTATION.md` · `DEPLOYMENT.md` · `VERIFICATION.md`.
