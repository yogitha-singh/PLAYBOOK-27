import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.analytics import config as acfg
from app.core.config import load_settings
from app.main import create_app

HAVE = (acfg.PROCESSED_DIR / "scenario_chase_states.csv").exists() and (acfg.MODEL_DIR / "wp_hgb.joblib").exists()


@unittest.skipUnless(HAVE, "run scripts/run_pipeline.py first")
class Scenario(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = create_app(load_settings(env="test", db_path=":memory:", serve_frontend=False)).test_client()

    def sim(self, **q): return self.c.get("/api/v1/scenario/simulate", query_string=q)

    def test_sections_are_separated_and_labelled(self):
        j = self.sim(innings=2, runs_required=45, balls_remaining=24, wickets_remaining=4, explain=1).json
        self.assertIn("MODEL-GENERATED", j["model_estimates"]["type"]); self.assertIn("HISTORICAL", j["historical_observations"]["type"])
        self.assertIn("HISTORICAL", j["player_evidence"]["type"]); self.assertIn("not causal", j["local_explanation"]["type"])
        self.assertNotIn("win_rate", str(j["model_estimates"]).lower().replace("win_probability", ""))   # history never leaks into the model section

    def test_probabilities_and_monotonic_logic(self):
        wp = [self.sim(innings=2, runs_required=r, balls_remaining=30, wickets_remaining=5).json["model_estimates"]["batting_side_win_probability"] for r in (20, 40, 60, 80)]
        self.assertTrue(all(0 <= x <= 1 for x in wp)); self.assertEqual(wp, sorted(wp, reverse=True))
        w = [self.sim(innings=2, runs_required=40, balls_remaining=30, wickets_remaining=k).json["model_estimates"]["batting_side_win_probability"] for k in (2, 5, 8)]
        self.assertEqual(w, sorted(w))

    def test_historical_frequency_is_valid_and_comparable(self):
        h = self.sim(innings=2, runs_required=45, balls_remaining=24, wickets_remaining=4).json["historical_observations"]
        self.assertTrue(h["available"]); lo, hi = h["wilson_95_interval"]; self.assertTrue(lo <= h["historical_win_rate"] <= hi)
        self.assertLess(abs(h["average_pooled_state"]["runs_required"] - 45), 4); self.assertGreaterEqual(h["match_state_observations"], 40)

    def test_edge_state_carries_comparability_warning(self):
        h = self.sim(innings=2, runs_required=12, balls_remaining=6, wickets_remaining=6).json["historical_observations"]
        self.assertTrue(any("balls remaining" in w for w in h["comparability_warnings"]))

    def test_player_evidence_only_for_pressure_states_and_min_cell(self):
        low = self.sim(innings=1, score=62, balls_remaining=66, wickets_remaining=5).json["player_evidence"]
        self.assertEqual(low["batters"], []); self.assertIn("below the pressure threshold", low["message"])
        hi = self.sim(innings=2, runs_required=45, balls_remaining=24, wickets_remaining=4).json["player_evidence"]
        self.assertTrue(all(x["deliveries"] >= 15 for x in hi["batters"] + hi["bowlers"]))

    def test_local_explanation_excludes_fixed_inputs(self):
        ex = self.sim(innings=2, runs_required=45, balls_remaining=24, wickets_remaining=4, explain=1).json["local_explanation"]["effects"]
        self.assertEqual(set(ex), {"wp", "lev", "x_runs", "x_out"})
        for rows in ex.values(): self.assertTrue(all(r["feature"] not in ("innings", "is_ipl") for r in rows))

    def test_validation(self):
        for q in ({"innings": 3}, {"innings": 2, "balls_remaining": 24, "wickets_remaining": 4}, {"innings": 2, "runs_required": 45, "balls_remaining": 0, "wickets_remaining": 4},
                  {"innings": 2, "runs_required": 45, "balls_remaining": 24, "wickets_remaining": 11}, {"innings": 2, "runs_required": "x", "balls_remaining": 24, "wickets_remaining": 4},
                  {"innings": 1, "balls_remaining": 24, "wickets_remaining": 4}, {"innings": 2, "runs_required": 4.5, "balls_remaining": 24, "wickets_remaining": 4},
                  {"innings": 2, "runs_required": 45, "balls_remaining": 24, "wickets_remaining": 4, "tier": "xx"}):
            r = self.sim(**q); self.assertEqual(r.status_code, 400, q); self.assertIn("code", r.json["error"])

    def test_presets_all_run(self):
        for p in self.c.get("/api/v1/scenario/presets").json["presets"]:
            q = {k: v for k, v in p.items() if k not in ("id", "label", "note")}
            self.assertEqual(self.sim(**q).status_code, 200, p["id"])

    def test_player_decomposition_reconciles(self):
        for role, ep in (("bat", "batters"), ("bowl", "bowlers")):
            pid = self.c.get(f"/api/v1/{ep}/rankings?page_size=1").json["items"][0]["player_id"]
            j = self.c.get(f"/api/v1/players/{pid}/explain?role={role}").json
            self.assertAlmostEqual(j["check_sum"], j["PRI"], delta=0.02)       # components sum to the published PRI
        low = self.c.get("/api/v1/batters/rankings?status=low_confidence&page_size=1").json["items"][0]["player_id"]
        self.assertEqual(self.c.get(f"/api/v1/players/{low}/explain?role=bat").status_code, 409)


if __name__ == "__main__":
    unittest.main()
