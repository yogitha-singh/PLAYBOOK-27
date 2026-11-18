"""Read-only access to the pipeline's derived outputs (player-level aggregates; never delivery-level data)."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import numpy as np
import pandas as pd

ROLES = {"bat": "batters", "bowl": "bowlers"}


def to_records(df: pd.DataFrame) -> list[dict]:
    out = df.astype(object).where(df.notna(), None)
    recs = out.to_dict("records")
    return [{k: (v.item() if hasattr(v, "item") else v) for k, v in r.items()} for r in recs]


class AnalyticsRepo:
    def __init__(self, processed_dir: Path):
        self.dir, self._lock, self._cache = Path(processed_dir), threading.Lock(), {}

    def available(self) -> bool:
        return (self.dir / "rankings_batters.csv").exists() and (self.dir / "rankings_bowlers.csv").exists()

    def _get(self, key, loader):
        with self._lock:
            if key not in self._cache:
                self._cache[key] = loader()
            return self._cache[key]

    def reload(self):
        with self._lock:
            self._cache.clear()

    def rankings(self, role: str) -> pd.DataFrame:
        def load():
            d = pd.read_csv(self.dir / f"rankings_{ROLES[role]}.csv")
            for c in ("rank", "rank_lo", "rank_hi", "grid_best_rank", "grid_worst_rank"):
                if c in d:
                    d[c] = d[c].round().astype("Int64")
            return d
        return self._get(("rank", role), load)

    def csv(self, name: str) -> pd.DataFrame:
        return self._get(("csv", name), lambda: pd.read_csv(self.dir / name))

    def json(self, name: str):
        return self._get(("json", name), lambda: json.loads((self.dir / name).read_text()))

    def player_ids(self) -> set[int]:
        return set(self.rankings("bat").player_id) | set(self.rankings("bowl").player_id)
