"""Integrity checks on the pipeline outputs (skipped if the pipeline has not been run)."""
import json, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd

from app.analytics import config

P = config.PROCESSED_DIR
HAVE = (P / "rankings_batters.csv").exists()


@unittest.skipUnless(HAVE, "run scripts/run_pipeline.py first")
class Outputs(unittest.TestCase):
    def setUp(self):
        self.bat = pd.read_csv(P / "rankings_batters.csv"); self.bowl = pd.read_csv(P / "rankings_bowlers.csv")

    def test_ranks_unique_and_contiguous(self):
        for d in (self.bat, self.bowl):
            r = d[d.eligible]["rank"].sort_values().tolist()
            self.assertEqual(r, list(range(1, len(r) + 1)))
            self.assertEqual(d.player_id.duplicated().sum(), 0)

    def test_only_eligible_players_are_ranked(self):
        for d in (self.bat, self.bowl):
            self.assertTrue(d[~d.eligible]["rank"].isna().all())

    def test_eligibility_respects_minimum_sample(self):
        meta = json.loads((P / "reliability_parameters.json").read_text())
        for role, d in (("bat", self.bat), ("bowl", self.bowl)):
            e = d[d.eligible]
            self.assertTrue((e.pressure_deliveries >= meta[role]["min_pressure_deliveries"]).all())
            self.assertTrue((e.pressure_appearances >= meta[role]["min_appearances"]).all())

    def test_uncertainty_brackets_estimate(self):
        for d in (self.bat, self.bowl):
            e = d[d.eligible]
            self.assertTrue(((e.PRI_lo <= e.PRI + 1e-9) & (e.PRI <= e.PRI_hi + 1e-9)).mean() > 0.95)
            self.assertTrue((e.p_top10 >= 0).all() and (e.p_top10 <= 1).all())

    def test_conventional_stats_reconcile(self):
        e = self.bat[self.bat.eligible]
        self.assertTrue(((e.runs / e.balls * 100 - e.strike_rate).abs() < 1e-6).all())
        self.assertTrue((e.pressure_deliveries == e.p_balls).all())
        eb = self.bowl[self.bowl.eligible]
        self.assertTrue(((6 * eb.runs / eb.legal_balls - eb.economy).abs() < 1e-6).all())

    def test_no_raw_delivery_data_in_processed(self):
        forbidden = {"innings_ball_num", "striker_id", "bowler_id", "overid", "over_ball_num", "dismissal_type", "match_id"}
        for f in P.glob("*.csv"):
            d = pd.read_csv(f)
            self.assertFalse(forbidden & set(d.columns), f.name)
            if f.name.startswith("scenario_") and f.name.endswith("_states.csv"):
                self.assertGreaterEqual(d.match_visits.min(), 5, f.name)          # small-cell suppression
            elif f.name.startswith("scenario_player_bins"):
                self.assertGreaterEqual(d.deliveries.min(), 15, f.name)
            else:
                self.assertLess(len(d), 5000, f.name)

    def test_units_are_consistent_between_ranking_and_profile(self):
        b = self.bat[self.bat.pressure_deliveries > 0]; w = self.bowl[self.bowl.pressure_deliveries > 0]
        self.assertTrue((b.pressure_deliveries == b.p_balls).all() and (b.pressure_legal_balls == b.p_balls).all())      # batters: deliveries == balls faced
        self.assertTrue((w.pressure_legal_balls == w.p_legal_balls).all())                                               # bowlers: legal balls reported separately
        self.assertTrue((w.pressure_deliveries >= w.pressure_legal_balls).all())                                         # deliveries include wides/no-balls

    def test_model_metrics_match_model_card(self):
        card = (Path(__file__).resolve().parents[2] / "docs" / "MODEL_CARD.md").read_text()
        m = json.loads((P / "model_metrics.json").read_text())["tasks"]
        for t, key in (("x_runs", "R2"), ("x_out", "ROC_AUC"), ("x_bwk", "ROC_AUC"), ("wp", "ROC_AUC"), ("wp", "LogLoss"), ("lev", "R2")):
            v = m[t]["test_metrics"][m[t]["selected_model"]][key]
            self.assertIn(f"{v:.3f}", card, f"{t} {key}={v:.3f} not found in MODEL_CARD.md")

    def test_validation_report_has_no_fail(self):
        rep = json.loads((P / "validation_report.json").read_text())
        self.assertEqual(rep["summary"]["FAIL"], 0)

    def test_model_metrics_are_recorded_not_invented(self):
        m = json.loads((P / "model_metrics.json").read_text())["tasks"]
        for t in ("x_runs", "x_out", "x_charged", "x_bwk", "wp", "lev"):
            self.assertIn("test_metrics", m[t]); self.assertIn("valid_selection", m[t])
            sel = m[t]["selected_model"]; self.assertIn(sel, m[t]["test_metrics"])


if __name__ == "__main__":
    unittest.main()
