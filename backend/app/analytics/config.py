"""Central configuration for the PLAYBOOK 27 analytics pipeline.

Every tunable constant lives here so a rerun is fully reproducible and every
analytical decision is visible in one place (see docs/METHODOLOGY.md).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _p(env: str, default: str) -> Path:
    p = Path(os.environ.get(env, default))
    return p if p.is_absolute() else (ROOT / p).resolve()


RAW_DIR = _p("PLAYBOOK_RAW_DIR", "data/raw")
INTERIM_DIR = _p("PLAYBOOK_INTERIM_DIR", "data/interim")
PROCESSED_DIR = _p("PLAYBOOK_PROCESSED_DIR", "data/processed")
MODEL_DIR = _p("PLAYBOOK_MODEL_DIR", "models")
SEED = int(os.environ.get("PLAYBOOK_SEED", "27"))

RAW_FILES = {
    "ball_by_ball": "ball_by_ball.csv",
    "matches": "matches.csv",
    "competitions": "competitions.csv",
    "teams": "teams.csv",
    "playing_eleven": "playing_eleven.csv",
    "mapping": "competition_team_player_mapping.csv",
}

# Columns that describe the OUTCOME/manner of a delivery. They are only known
# after the ball is bowled and therefore MUST NOT be used as model inputs.
LEAKY_COLUMNS = ["stroke", "delivery_style", "bowl_speed", "on_or_off", "over_or_around",
                 "runs", "is_four", "is_six", "is_wicket", "dismissal_type", "dismissed_player_id",
                 "extras_type", "extras1_runs", "extras_2_runs", "delivery_ist_time"]

STANDARD_BALLS = 120          # T20 innings length
WICKETS = 10
PHASES = {"Powerplay": (0, 6), "Middle": (6, 15), "Death": (15, 20)}  # 0-based over index [lo, hi)

# Chronological split for honest forward-looking model evaluation
TRAIN_END = "2024-12-31"      # train: matches up to and including this date
VALID_END = "2025-07-31"      # validation: (TRAIN_END, VALID_END]; test: after VALID_END
CV_FOLDS = 5                  # match-grouped folds for cross-fitted (out-of-fold) expectations

ELO_K = 24.0
ELO_START = 1500.0
VENUE_PRIOR_STRENGTH = 5.0


@dataclass
class PressureConfig:
    """Pressure categories are quantiles of the pre-delivery Leverage Index."""
    name: str = "primary"
    cuts: tuple = (0.50, 0.80, 0.95)               # Low<Q50<=Moderate<Q80<=High<Q95<=Critical
    pressure_levels: tuple = ("High", "Critical")  # what counts as "pressure" in player evaluation
    by_innings: bool = True                        # quantiles computed separately for setting (inn 1) and chasing (inn 2)
