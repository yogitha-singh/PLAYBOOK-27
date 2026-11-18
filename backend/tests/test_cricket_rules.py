"""Cricket-scoring rules on hand-built deliveries (no proprietary data needed)."""
import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

from app.analytics import clean, features


def mini_raw():
    rows = [  # innings 1, one over + extras; columns follow the data pack schema
        # id, runs, extras_type, e1, e2, wicket, dismissal, dismissed
        (1, 0, None, 0, 0, False, None, None),          # dot
        (2, 4, None, 0, 0, False, None, None),          # four
        (3, 0, "wide", 1, 0, False, None, None),        # wide: not legal, not faced, 1 run to bowler
        (4, 2, "Overstep", 1, 0, False, None, None),    # no-ball + 2 off bat: not legal, faced, bowler concedes 3
        (5, 0, "legbyes", 2, 0, False, None, None),     # leg byes: legal, faced, bowler concedes 0
        (6, 0, None, 0, 0, True, "Run Out", 11),        # run out of the NON-striker: not a batter_out for striker, not a bowler wicket
        (7, 0, None, 0, 0, True, "Bowled", 10),         # bowled
        (8, 0, None, 0, 0, True, "Retire Out", 10),     # retired: team wicket, not a dismissal
        (9, 0, "penalty", 5, 0, False, None, None),     # penalty runs: not a delivery
    ]
    b = pd.DataFrame([dict(match_id=1, innings=1, overid=1, over_ball_num=i, innings_ball_num=i, batting_team_id=1, bowling_team_id=2, striker_id=10,
                           striker_name="A", non_striker_id=11, bowler_id=20, bowler_name="B", batting_type="RHB", bowling_type="x", batting_order=1,
                           runs=r, is_four=r == 4, is_six=False, is_wicket=w, dismissal_type=dt, dismissed_player_id=dp, extras_type=et,
                           extras1_runs=e1, extras_2_runs=e2, pace_or_spin="Pace") for i, r, et, e1, e2, w, dt, dp in rows])
    m = pd.DataFrame([dict(match_id=1, comp_id=1, match_date="2024-04-01", stage="League", venue_id=1, home_team_id=1, away_team_id=2, toss_win_team_id=1,
                           toss_opted="Bat", first_inn_revised_overs=np.nan, second_inn_revised_overs=np.nan, revised_target=np.nan, win_team_id=1, result="x won")])
    c = pd.DataFrame([dict(comp_id=1, comp_name="Indian Premier League", match_format="T20", season=2024)])
    return {"ball_by_ball": b, "matches": m, "competitions": c}


class CricketRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = mini_raw()
        cls.matches = clean.build_matches(raw)
        cls.b, cls.log = clean.clean_deliveries(raw, cls.matches)
        cls.b = cls.b.set_index("innings_ball_num")

    def test_legal_and_faced(self):
        b = self.b
        self.assertEqual(list(b.legal), [True, True, False, False, True, True, True, True, False])
        self.assertEqual(list(b.faced), [True, True, False, True, True, True, True, True, False])

    def test_bowler_runs_charge(self):
        b = self.b
        self.assertEqual(list(b.bowler_runs), [0, 4, 1, 3, 0, 0, 0, 0, 0])   # wide=1, noball=1+2, legbyes not charged, penalty not charged

    def test_total_runs_include_extras(self):
        self.assertEqual(list(self.b.total_runs), [0, 4, 1, 3, 2, 0, 0, 0, 5])

    def test_wicket_attribution(self):
        b = self.b
        self.assertEqual(list(b.bowler_wkt), [False] * 5 + [False, True, False, False])   # run-out & retire-out not credited to bowler
        self.assertEqual(list(b.batter_out), [False] * 5 + [False, True, False, False])   # run-out of non-striker is not the striker's dismissal
        self.assertEqual(int(b.team_wicket.sum()), 3)                                       # but all three fall for the team

    def test_state_features_are_pre_delivery(self):
        s = self.b.reset_index()
        s["in_scope"] = True; s["inn1_total"] = np.nan
        s = features.add_state_features(s, self.matches).set_index("innings_ball_num")
        self.assertEqual(s.loc[1, "score_before"], 0)
        self.assertEqual(s.loc[3, "score_before"], 4)             # sees only balls 1-2
        self.assertEqual(s.loc[7, "wkts_before"], 1)              # the run-out on ball 6 is visible from ball 7, not ball 6
        self.assertEqual(s.loc[6, "wkts_before"], 0)
        self.assertEqual(s.loc[4, "balls_rem"], 118)              # wide did not use a legal ball

    def test_leakage_guard(self):
        features.assert_no_leakage(features.CONTEXT_FEATURES)
        features.assert_no_leakage(features.WP_FEATURES)
        with self.assertRaises(AssertionError):
            features.assert_no_leakage(["balls_rem", "runs"])


if __name__ == "__main__":
    unittest.main()
