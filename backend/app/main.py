"""Application factory."""
from __future__ import annotations

import logging
import math
import time
import uuid

from flask import Flask, g, jsonify, request, send_from_directory
from flask.json.provider import DefaultJSONProvider

from .analytics import config as acfg
from .api.routes import bp
from .core.config import Settings, load_settings
from .core.logging import log_fields, setup_logging
from .core.security import ApiError, RateLimiter, apply_security_headers
from .database import db
from .repositories.analytics_repo import AnalyticsRepo
from .services.scenario import ModelStore

log = logging.getLogger("playbook.api")


def _clean(o):
    """RFC 8259 has no NaN/Infinity: browsers' response.json() rejects them, so emit null instead."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


class StrictJSONProvider(DefaultJSONProvider):
    def dumps(self, obj, **kw):
        return super().dumps(_clean(obj), **kw)


def create_app(settings: Settings | None = None) -> Flask:
    s = settings or load_settings()
    setup_logging()
    app = Flask(__name__, static_folder=None)
    app.config["SETTINGS"] = s
    app.json = StrictJSONProvider(app)
    app.json.sort_keys = False
    conn = db.connect(s.db_path)
    applied = db.migrate(conn)
    if applied: log.info("applied migrations: %s", applied)
    app.config["DB"], app.config["REPO"], app.config["MODELS"] = conn, AnalyticsRepo(s.processed_dir), ModelStore(s.model_dir)
    limiter = RateLimiter(s.rate_limit_per_min)
    app.register_blueprint(bp)

    @app.before_request
    def _start():
        g.t0, g.rid = time.perf_counter(), request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        if request.path.startswith("/api/") and not limiter.check(request.remote_addr or "anon"):
            raise ApiError(429, "rate_limited", "too many requests")
        if request.method == "OPTIONS" and request.headers.get("Origin") in s.cors_origins:
            return "", 204

    @app.after_request
    def _finish(resp):
        origin = request.headers.get("Origin")
        if origin and origin in s.cors_origins:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
            resp.headers["Vary"] = "Origin"
        resp.headers["X-Request-ID"] = getattr(g, "rid", "-")
        if request.path.startswith("/api/"):
            log_fields(log, "request", rid=g.rid, method=request.method, path=request.path, status=resp.status_code, ms=round(1000 * (time.perf_counter() - g.t0), 1))
        return apply_security_headers(resp)

    @app.errorhandler(ApiError)
    def _api_err(e): return jsonify(error={"code": e.code, "message": e.message}), e.status

    @app.errorhandler(404)
    def _404(e): return jsonify(error={"code": "not_found", "message": "resource not found"}), 404

    @app.errorhandler(405)
    def _405(e): return jsonify(error={"code": "method_not_allowed", "message": "method not allowed"}), 405

    @app.errorhandler(Exception)
    def _500(e):
        log.exception("unhandled error")
        return jsonify(error={"code": "internal_error", "message": "unexpected server error", "request_id": getattr(g, "rid", None)}), 500

    if s.serve_frontend:
        fe = acfg.ROOT / "frontend"

        @app.get("/")
        def index(): return send_from_directory(fe, "index.html") if (fe / "index.html").exists() else (jsonify(name="PLAYBOOK 27", docs="/api/v1/health"), 200)

        @app.get("/<path:p>")
        def static_files(p):
            if p.startswith("api/"): raise ApiError(404, "not_found", "resource not found")
            return send_from_directory(fe, p)
    return app
