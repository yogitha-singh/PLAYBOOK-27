"""Environment-driven settings. No secrets in code: the API key is read from PLAYBOOK_API_KEY."""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from ..analytics import config as acfg


@dataclass(frozen=True)
class Settings:
    env: str = "production"                       # development | production | test
    api_key: str | None = None                    # required for write/admin endpoints (unless env == development)
    cors_origins: tuple = ()                      # explicit allow-list, empty = same-origin only
    rate_limit_per_min: int = 240
    db_path: Path = Path("data/app.sqlite3")
    processed_dir: Path = acfg.PROCESSED_DIR
    model_dir: Path = acfg.MODEL_DIR
    serve_frontend: bool = True
    max_page_size: int = 200

    def with_(self, **kw) -> "Settings":
        return replace(self, **kw)


def load_settings(**override) -> Settings:
    env = os.environ.get("PLAYBOOK_ENV", "production")
    origins = tuple(o.strip() for o in os.environ.get("PLAYBOOK_CORS_ORIGINS", "").split(",") if o.strip())
    db = Path(os.environ.get("PLAYBOOK_DB_PATH", acfg.ROOT / "data" / "app.sqlite3"))
    s = Settings(env=env, api_key=os.environ.get("PLAYBOOK_API_KEY") or None, cors_origins=origins,
                 rate_limit_per_min=int(os.environ.get("PLAYBOOK_RATE_LIMIT", "240")), db_path=db)
    return s.with_(**override) if override else s
