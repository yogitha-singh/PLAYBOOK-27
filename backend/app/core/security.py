"""API-key auth, sliding-window rate limiting and security headers."""
from __future__ import annotations

import hmac
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import current_app, request


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def require_key(fn):
    """Write/admin endpoints. In production an API key is mandatory; if none is configured, writes are refused (fail closed)."""
    @wraps(fn)
    def wrapper(*a, **kw):
        s = current_app.config["SETTINGS"]
        if s.env == "development" and not s.api_key:
            return fn(*a, **kw)
        if not s.api_key:
            raise ApiError(503, "auth_not_configured", "write endpoints are disabled: PLAYBOOK_API_KEY is not configured")
        given = request.headers.get("X-API-Key", "")
        if not hmac.compare_digest(given.encode(), s.api_key.encode()):
            raise ApiError(401, "unauthorized", "missing or invalid API key")
        return fn(*a, **kw)
    return wrapper


class RateLimiter:
    def __init__(self, per_min: int):
        self.per_min, self.hits, self.lock = per_min, defaultdict(deque), threading.Lock()

    def check(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_min:
                return False
            q.append(now)
            return True


def apply_security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Cache-Control", "no-store" if request.path.startswith("/api/") else "public, max-age=300")
    resp.headers.setdefault("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'")
    return resp
