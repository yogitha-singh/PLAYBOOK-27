"""Raw data extraction + schema validation. Raw files are only ever READ."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from . import config

log = logging.getLogger("playbook.ingest")

EXPECTED_COLUMNS = {
    "ball_by_ball": ["match_id", "innings", "overid", "over_ball_num", "innings_ball_num", "batting_team_id",
                     "bowling_team_id", "striker_id", "striker_name", "non_striker_id", "bowler_id", "bowler_name",
                     "batting_type", "bowling_type", "batting_order", "runs", "is_four", "is_six", "is_wicket",
                     "dismissal_type", "dismissed_player_id", "extras_type", "extras1_runs", "extras_2_runs",
                     "pace_or_spin"],
    "matches": ["match_id", "comp_id", "match_date", "stage", "venue_id", "home_team_id", "away_team_id",
                "toss_win_team_id", "toss_opted", "first_inn_revised_overs", "second_inn_revised_overs",
                "revised_target", "win_team_id", "result"],
    "competitions": ["comp_id", "comp_name", "match_format", "season"],
    "teams": ["comp_id", "team_id", "team_name"],
    "playing_eleven": ["match_id", "team_id", "player_id", "batting_order", "is_played"],
    "mapping": ["comp_id", "team_id", "team_name", "player_id", "player_name"],
}


class SchemaError(ValueError):
    pass


def load_raw(raw_dir: Path | None = None) -> dict[str, pd.DataFrame]:
    raw_dir = Path(raw_dir or config.RAW_DIR)
    out = {}
    for key, fname in config.RAW_FILES.items():
        path = raw_dir / fname
        if not path.exists():
            raise FileNotFoundError(f"Missing raw file {path}. Set PLAYBOOK_RAW_DIR to the data pack folder.")
        df = pd.read_csv(path, low_memory=False)
        missing = [c for c in EXPECTED_COLUMNS[key] if c not in df.columns]
        if missing:
            raise SchemaError(f"{fname}: missing expected columns {missing}")
        out[key] = df
        log.info("loaded %-14s rows=%-7d cols=%d", key, len(df), df.shape[1])
    return out
