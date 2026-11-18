# DEPLOYMENT — status: **not deployed. No public URL exists.** Everything below is prepared but, where stated, unverified.
## Confidentiality rules
Never commit or upload the raw data pack. The image/host receives only `data/processed/` (aggregates, small cells suppressed) and `models/`. `.gitignore` excludes `data/raw`, `data/interim`, CSV names of the pack, `__*`, `.env`, `models/*.joblib`.
## Build the deployable artefacts (on your machine, where the raw data lives)
1. `pip install -r backend/requirements.txt` · 2. `PLAYBOOK_RAW_DIR=/path/to/pack python scripts/run_pipeline.py` (~3 min; writes `data/processed/` and `models/`)
3. `python scripts/verify_backend.py` (writes `docs/VERIFICATION.md`). Because `models/*.joblib` are gitignored, build the image locally or in CI **after** running the pipeline there; do not expect them from git.
## Run locally
`cd backend && PLAYBOOK_ENV=development python -m flask --app wsgi run` (development mode allows shortlist writes without a key). Production: set `PLAYBOOK_API_KEY`; `gunicorn -w 2 -b 0.0.0.0:8000 wsgi:app` from `backend/`.
Docker (**untested here — Docker not available**): `cp .env.example .env` (set PLAYBOOK_API_KEY), `docker compose up --build`; health: `GET /api/v1/health`, readiness: `GET /api/v1/health/ready`.
## Hosting options (not evaluated against live pricing — verify before choosing)
A single container (Render/Railway/Fly.io or similar) can serve API + static frontend from one origin, which avoids CORS. SQLite needs a persistent volume (compose mounts one); for multiple instances move shortlist storage to PostgreSQL (the repository/service split makes this a contained change). Rate limiting is per process.
## Checklist before going public
API key set; `PLAYBOOK_CORS_ORIGINS` explicit; HTTPS terminated by the host; confirm competition rules permit hosting derived outputs (the pack "must not be shared or published" — player-level aggregates are derived but you must make that call); remove or restrict `/admin/status` if undesired.
## Not done
No deployment, no production smoke test, no Docker build, no GitHub Actions run, no load test.
