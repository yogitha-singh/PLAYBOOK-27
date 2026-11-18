#!/usr/bin/env python
"""PLAYBOOK 27 end-to-end pipeline:  raw CSVs -> validation -> cleaning -> features -> models -> pressure -> reliability
-> uncertainty/stability -> ranking tables (data/processed).  Raw files are only read.

  PLAYBOOK_RAW_DIR=/path/to/datapack python scripts/run_pipeline.py [--reuse-expectations] [--boot 300]

--reuse-expectations skips model training and reloads the cached (gitignored) analytical dataset from data/interim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import platform
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from app.analytics import scenario as scn
from app.analytics import clean, config, features, ingest, pressure, profiles, reliability as R, stability as S, validate, value, engine
from app.ml import models as M

PIPELINE_VERSION = "1.0.0"
log = logging.getLogger("playbook.pipeline")


def _finite(o):
    if isinstance(o, float):
        return o if np.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _finite(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_finite(v) for v in o]
    return o


def jdump(obj, name):
    """Strict JSON: undefined statistics (NaN/inf) are written as null so every consumer (incl. browsers) can parse the file."""
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    (config.PROCESSED_DIR / name).write_text(json.dumps(_finite(obj), indent=1, allow_nan=False, default=lambda o: _finite(o.item()) if hasattr(o, "item") else str(o)))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reuse-expectations", action="store_true")
    ap.add_argument("--boot", type=int, default=300)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    t0 = time.time()
    steps = []
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True); config.INTERIM_DIR.mkdir(parents=True, exist_ok=True)

    raw = ingest.load_raw(); steps.append("ingest+schema validation")
    matches = clean.build_matches(raw)
    b, clog = clean.clean_deliveries(raw, matches)
    b, slog = clean.flag_analysis_scope(b)
    clog.update(slog); jdump(clog, "cleaning_log.json")
    rep = validate.run_validation(raw, matches, b)
    jdump({"summary": validate.summarise(rep), "checks": rep}, "validation_report.json")
    if any(c["status"] == "FAIL" for c in rep):
        raise SystemExit("validation FAILED: " + str([c for c in rep if c["status"] == "FAIL"]))
    steps.append("cleaning + validation")
    b = features.add_state_features(b, matches); steps.append("feature engineering")

    cache = config.INTERIM_DIR / "analytical_dataset.pkl"
    if a.reuse_expectations and cache.exists():
        s = pd.read_pickle(cache); meta = json.loads((config.PROCESSED_DIR / "model_metrics.json").read_text()); log.info("reusing cached expectations")
    else:
        from app.ml import train
        s, meta = train.train_all(b)
        s.to_pickle(cache); jdump(meta, "model_metrics.json"); steps.append("model training + cross-fitting")

    s, pinfo = pressure.assign(s)
    jdump(pinfo, "pressure_thresholds.json")
    pressure.validity_table(s).to_csv(config.PROCESSED_DIR / "pressure_validity.csv", index=False)
    pressure.phase_by_category(s).to_csv(config.PROCESSED_DIR / "pressure_phase_mix.csv")
    pressure.pressure_rate_by_over(s).to_csv(config.PROCESSED_DIR / "pressure_by_over.csv", index=False)
    wc = value.estimate_wicket_cost(s); jdump(wc, "wicket_cost.json"); V = wc["V"]
    s = value.add_values(s, V)

    # evidence tables for the scenario simulator (aggregated; small cells suppressed)
    P_ = config.PROCESSED_DIR
    scn.chase_states(s).to_csv(P_ / "scenario_chase_states.csv", index=False)
    scn.setting_states(s).to_csv(P_ / "scenario_setting_states.csv", index=False)
    scn.league_bins(s).to_csv(P_ / "scenario_league_bins.csv", index=False)
    scn.player_bins(s, "bat").to_csv(P_ / "scenario_player_bins_batters.csv", index=False)
    scn.player_bins(s, "bowl").to_csv(P_ / "scenario_player_bins_bowlers.csv", index=False)
    jdump(scn.feature_medians(s, features.CONTEXT_FEATURES + ["wp_pre"]), "feature_medians.json")
    steps.append("scenario evidence tables")

    names = profiles.display_names(raw); teams = profiles.latest_teams(s, raw["teams"])
    rb, rw = profiles.batter_role(s), profiles.bowler_role(s)
    # minimum sample is derived inside evaluate_role; the grid needs it first
    mins = {}
    for role, (pid, cols) in engine.ROLE_COLS.items():
        P = R.build_role_panel(s, pid, cols, s.is_pressure, V); mins[role] = R.derive_min_sample(R.components(P), P.A.var_p)
    grid = S.sensitivity_grid(s, V, mins, engine.MIN_APPEARANCES); steps.append("sensitivity grid")
    dates = s.groupby("match_id").match_date.first()
    out_meta = {"V": wc, "pressure": pinfo}
    for role, roles, tag in (("bat", rb, "batters"), ("bowl", rw, "bowlers")):
        d, rmeta = engine.evaluate_role(s, role, V, names, teams, roles, grid, n_boot=a.boot)
        d.to_csv(config.PROCESSED_DIR / f"rankings_{tag}.csv", index=False)
        d[d["rank"] <= 20].to_csv(config.PROCESSED_DIR / f"final_top20_{tag}.csv", index=False)
        g, ncfg, _ = grid[role]
        g.assign(player=g.index.map(names), n_configs=ncfg).to_csv(config.PROCESSED_DIR / f"sensitivity_{tag}.csv")
        pid, cols = engine.ROLE_COLS[role]
        P = R.build_role_panel(s, pid, cols, s.is_pressure, V)
        S.split_half(P, engine.W_PRIMARY, 50, reps=60).to_csv(config.PROCESSED_DIR / f"split_half_{tag}.csv", index=False)
        temporal = [S.temporal_validity(P, dates, cut, engine.W_PRIMARY, int(0.6 * rmeta["min_pressure_deliveries"]), 40) for cut in ("2025-03-31", "2025-07-31")]
        jdump(temporal, f"temporal_validity_{tag}.json")
        out_meta[role] = rmeta
        log.info("%s: eligible=%d min_balls=%d", tag, rmeta["n_eligible"], rmeta["min_pressure_deliveries"])
    jdump(out_meta, "reliability_parameters.json"); steps.append("player evaluation + stability")

    man = {"pipeline_version": PIPELINE_VERSION, "model_version": M.MODEL_VERSION, "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "seed": config.SEED, "python": platform.python_version(), "elapsed_seconds": round(time.time() - t0, 1), "steps": steps,
           "raw_files": {k: {"rows": int(len(df)), "sha256": sha256(config.RAW_DIR / config.RAW_FILES[k])} for k, df in raw.items()},
           "in_scope": {"matches": int(s.match_id.nunique()), "deliveries": int(len(s)), "pressure_deliveries": int(s.is_pressure.sum())},
           "date_range": [str(s.match_date.min().date()), str(s.match_date.max().date())]}
    jdump(man, "dataset_manifest.json")
    log.info("done in %.0fs", time.time() - t0)


if __name__ == "__main__":
    main()
