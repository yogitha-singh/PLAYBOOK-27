#!/usr/bin/env python
"""Backend verification harness. Starts the REAL Flask app on a local port, calls every route over HTTP and writes docs/VERIFICATION.md
from the actual results. Nothing here is hand-written: if a check fails it is recorded as FAIL."""
from __future__ import annotations

import json, os, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.update(PLAYBOOK_ENV="production", PLAYBOOK_API_KEY="verify-key", PLAYBOOK_DB_PATH=str(Path(tempfile.mkdtemp()) / "v.sqlite3"), PLAYBOOK_RATE_LIMIT="60")
from werkzeug.serving import make_server
from app.main import create_app

app = create_app()
srv = make_server("127.0.0.1", 0, app, threaded=True)
BASE = f"http://127.0.0.1:{srv.server_port}"
threading.Thread(target=srv.serve_forever, daemon=True).start()
results = []


def call(method, path, headers=None, data=None):
    req = urllib.request.Request(BASE + path, method=method, headers=headers or {}, data=json.dumps(data).encode() if data is not None else None)
    if data is not None: req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r: return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e: return e.code, e.read(), dict(e.headers)


def check(name, ok, detail=""): results.append((name, "PASS" if ok else "FAIL", detail))


K = {"X-API-Key": "verify-key"}
s, b, _ = call("GET", "/api/v1/batters/rankings?page_size=1"); bid = json.loads(b)["items"][0]["player_id"]
s, b, _ = call("GET", "/api/v1/bowlers/rankings?page_size=2"); bw = [i["player_id"] for i in json.loads(b)["items"]]
cases = [("GET", "/api/v1/health", 200), ("GET", "/api/v1/health/ready", 200), ("GET", "/api/v1/overview", 200), ("GET", "/api/v1/batters/rankings", 200), ("GET", "/api/v1/bowlers/rankings", 200),
         ("GET", "/api/v1/players?q=kumar", 200), ("GET", f"/api/v1/players/{bid}", 200), (f"GET", f"/api/v1/players/{bid}/explain?role=bat", 200),
         ("GET", f"/api/v1/players/compare?role=bowl&ids={bw[0]},{bw[1]}", 200), ("GET", "/api/v1/pressure/overview", 200), ("GET", "/api/v1/pressure/distribution", 200),
         ("GET", "/api/v1/models/metrics", 200), ("GET", "/api/v1/models/feature-importance?task=lev", 200), ("GET", "/api/v1/methodology/validation", 200),
         ("GET", "/api/v1/scenario/presets", 200), ("GET", "/api/v1/scenario/simulate?innings=2&runs_required=45&balls_remaining=24&wickets_remaining=4&explain=1", 200),
         ("GET", "/api/v1/scouting/recommendations?role=bat", 200), ("GET", "/api/v1/scouting/shortlist", 200), ("GET", "/api/v1/exports/rankings/bat.csv", 200),
         ("GET", "/api/v1/exports/shortlist.csv", 200), ("GET", f"/api/v1/scouting/report/bat/{bid}.pdf", 200)]
for m, p, want in cases:
    s, b, h = call(m, p); check(f"{m} {p.split('?')[0]}", s == want, f"HTTP {s}")
# auth / writes
check("POST shortlist without key -> 401", call("POST", "/api/v1/scouting/shortlist", data={"player_id": bid, "role": "bat"})[0] == 401)
check("POST shortlist wrong key -> 401", call("POST", "/api/v1/scouting/shortlist", {"X-API-Key": "x"}, {"player_id": bid, "role": "bat"})[0] == 401)
check("POST shortlist valid -> 201", call("POST", "/api/v1/scouting/shortlist", K, {"player_id": bid, "role": "bat", "note": "verify"})[0] == 201)
check("POST duplicate -> 409", call("POST", "/api/v1/scouting/shortlist", K, {"player_id": bid, "role": "bat"})[0] == 409)
check("PATCH note -> 200", call("PATCH", f"/api/v1/scouting/shortlist/{bid}?role=bat", K, {"note": "n2"})[0] == 200)
check("GET admin/status without key -> 401", call("GET", "/api/v1/admin/status")[0] == 401)
check("GET admin/status with key -> 200", call("GET", "/api/v1/admin/status", K)[0] == 200)
check("DELETE shortlist -> 204", call("DELETE", f"/api/v1/scouting/shortlist/{bid}?role=bat", K)[0] == 204)
check("DELETE again -> 404", call("DELETE", f"/api/v1/scouting/shortlist/{bid}?role=bat", K)[0] == 404)
# validation / errors
for p in ("/api/v1/batters/rankings?sort_by=x", "/api/v1/players/compare?ids=1", "/api/v1/scenario/simulate?innings=9"): check(f"400 on {p}", call("GET", p)[0] == 400)
s, b, h = call("GET", "/api/v1/nothing"); check("404 JSON error shape", s == 404 and "error" in json.loads(b))
s, b, h = call("DELETE", "/api/v1/health"); check("405 JSON error shape", s == 405 and "error" in json.loads(b))
s, b, h = call("GET", "/api/v1/health", {"X-Request-ID": "vrf-1"}); check("request id echoed + security headers", h.get("X-Request-ID") == "vrf-1" and h.get("X-Content-Type-Options") == "nosniff" and "Content-Security-Policy" in h)
s, b, h = call("OPTIONS", "/api/v1/health", {"Origin": "https://evil.example"}); check("CORS: unlisted origin gets no allow header", "Access-Control-Allow-Origin" not in h)
# SQL-injection / XSS payload stored inertly
call("POST", "/api/v1/scouting/shortlist", K, {"player_id": bid, "role": "bat", "note": "'); DROP TABLE shortlist;--<script>alert(1)</script>"})
s, b, _ = call("GET", "/api/v1/scouting/shortlist"); check("injection payload stored as inert text, table intact", s == 200 and json.loads(b)["count"] == 1)
call("DELETE", f"/api/v1/scouting/shortlist/{bid}?role=bat", K)
# rate limit (60/min configured): fire >60 requests
codes = [call("GET", "/api/v1/health")[0] for _ in range(70)]
check("rate limit returns 429 after the configured 60/min", 429 in codes, f"first 429 at request #{codes.index(429) + 1 if 429 in codes else 'never'} of 70 (earlier calls also count)")
srv.shutdown()

# static checks of deployment files (NOT a docker build)
df = (ROOT / "backend" / "Dockerfile").read_text()
copies = [l.split()[1] for l in df.splitlines() if l.startswith("COPY")]
missing = [c for c in copies if not (ROOT / c).exists()]
check("Dockerfile: every COPY source exists in repo", not missing, f"missing: {missing}" if missing else f"{len(copies)} COPY sources present")
import yaml
ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text()); check("CI workflow is valid YAML with jobs", "jobs" in ci and len(ci["jobs"]) >= 2, f"jobs: {list(ci['jobs'])}")
dc = yaml.safe_load((ROOT / "docker-compose.yml").read_text()); check("docker-compose.yml is valid YAML", "services" in dc)
t = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=ROOT / "backend", capture_output=True, text=True)
last = t.stderr.strip().splitlines()[-3:]
check("unittest suite (same command CI runs)", t.returncode == 0, " ".join(last))
import shutil
if shutil.which("node"):
    tn = subprocess.run(["node", "--test", "tests/shell.test.js", "tests/util_charts.test.js", "tests/contrast.test.js", "tests/pages.test.js"], cwd=ROOT / "frontend", capture_output=True, text=True)
    summ = [l.strip() for l in tn.stdout.splitlines() if l.startswith(("# tests", "# pass", "# fail"))]
    check("frontend node tests (live API page rendering, charts, contrast, router)", tn.returncode == 0, " ".join(summ))
t2 = subprocess.run([sys.executable, "-m", "compileall", "-q", "backend/app", "scripts"], cwd=ROOT, capture_output=True, text=True); check("python compileall (CI syntax step)", t2.returncode == 0)
routes = sorted({f"{m} {r.rule}" for r in app.url_map.iter_rules() if r.endpoint != "static" for m in r.methods if m not in ("HEAD", "OPTIONS")})
api_routes = [r for r in routes if "/api/v1" in r]
out = ["# VERIFICATION (generated by scripts/verify_backend.py — do not edit by hand)", f"Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. Server: werkzeug dev server on 127.0.0.1 (real HTTP, production env, API key set, rate limit 60/min).",
       f"\nAPI route+method combinations registered: **{len(api_routes)}**\n", "| Check | Result | Detail |", "|---|---|---|"]
out += [f"| {n} | {r} | {d} |" for n, r, d in results]
npass = sum(r == "PASS" for _, r, _ in results)
out += [f"\n**{npass}/{len(results)} checks passed.**", "\n## NOT verified in this environment",
        "- `docker build` / `docker compose up`: Docker is not installed here; only static checks above (COPY sources exist, YAML parses).",
        "- GitHub Actions execution: workflow parsed but never run on GitHub; the lint step (`ruff`) was not run locally (not installed).",
        "- gunicorn (production WSGI server) was not run; the Werkzeug server was used.",
        "- PostgreSQL / FastAPI / SQLAlchemy / Alembic: not used (see ARCHITECTURE.md).", "- Load/performance testing and multi-worker rate limiting (limiter is per-process in memory)."]
(ROOT / "docs" / "VERIFICATION.md").write_text("\n".join(out) + "\n")
print(f"{npass}/{len(results)} passed; {len(api_routes)} api route-methods")
for n, r, d in results:
    if r == "FAIL": print("FAIL:", n, d)
