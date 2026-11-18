import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd

from app.analytics import config as acfg
from app.core.config import load_settings
from app.main import create_app

P = acfg.PROCESSED_DIR
HAVE = (P / "rankings_batters.csv").exists()
KEY = {"X-API-Key": "test-key"}


def make(**kw):
    return create_app(load_settings(env="test", db_path=":memory:", api_key="test-key", serve_frontend=False, **kw)).test_client()


@unittest.skipUnless(HAVE, "run scripts/run_pipeline.py first")
class Api(unittest.TestCase):
    def setUp(self): self.c = make()

    def test_health_and_ready(self):
        self.assertEqual(self.c.get("/api/v1/health").json["status"], "ok")
        r = self.c.get("/api/v1/health/ready"); self.assertEqual(r.status_code, 200); self.assertEqual(r.json["checks"]["database"], "ok")

    def test_security_headers_and_request_id(self):
        r = self.c.get("/api/v1/health", headers={"X-Request-ID": "abc123"})
        self.assertEqual(r.headers["X-Request-ID"], "abc123"); self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff"); self.assertIn("Content-Security-Policy", r.headers)

    def test_overview_matches_pipeline(self):
        o = self.c.get("/api/v1/overview").json
        bat = pd.read_csv(P / "rankings_batters.csv")
        self.assertEqual(o["eligible_batters"], int(bat.eligible.sum()))
        self.assertEqual(o["top_batter"]["player"], bat[bat["rank"] == 1].player.iloc[0])

    def test_rankings_match_analytics_csv(self):
        for role, f in (("batters", "rankings_batters.csv"), ("bowlers", "rankings_bowlers.csv")):
            d = pd.read_csv(P / f); top = d[d.eligible].sort_values("rank").head(10)
            api = self.c.get(f"/api/v1/{role}/rankings?page_size=10").json
            self.assertEqual([i["player_id"] for i in api["items"]], top.player_id.tolist())
            self.assertEqual(api["total"], int(d.eligible.sum()))

    def test_sorting_filtering_pagination(self):
        r = self.c.get("/api/v1/batters/rankings?sort_by=pressure_deliveries&order=desc&page_size=5").json["items"]
        self.assertEqual([i["pressure_deliveries"] for i in r], sorted([i["pressure_deliveries"] for i in r], reverse=True))
        a = self.c.get("/api/v1/batters/rankings?tier=A&page_size=100").json
        self.assertTrue(all(i["tier"].startswith("A") for i in a["items"]))
        p2 = self.c.get("/api/v1/batters/rankings?page=2&page_size=10").json["items"]
        self.assertEqual(p2[0]["rank"], 11)
        self.assertEqual(self.c.get("/api/v1/batters/rankings?q=tim%20david").json["items"][0]["player"], "Tim David")
        self.assertEqual(self.c.get("/api/v1/batters/rankings?page_size=99999").json["page_size"], 200)   # capped

    def test_low_confidence_players_not_in_ranked_view(self):
        ranked = {i["player_id"] for i in self.c.get("/api/v1/batters/rankings?page_size=200").json["items"]}
        low = self.c.get("/api/v1/batters/rankings?status=low_confidence&page_size=200").json
        self.assertGreater(low["total"], 0); self.assertFalse(ranked & {i["player_id"] for i in low["items"]})

    def test_validation_errors(self):
        for u in ("/api/v1/batters/rankings?sort_by=hax", "/api/v1/batters/rankings?order=up", "/api/v1/batters/rankings?page=abc", "/api/v1/batters/rankings?status=zzz",
                  "/api/v1/players/compare?ids=1&role=bat", "/api/v1/players/compare?ids=a,b", "/api/v1/players/compare?ids=1,2&role=xx", "/api/v1/models/feature-importance?task=nope"):
            r = self.c.get(u); self.assertEqual(r.status_code, 400, u); self.assertIn("code", r.json["error"])

    def test_not_found_shape(self):
        r = self.c.get("/api/v1/players/999999999"); self.assertEqual(r.status_code, 404); self.assertEqual(r.json["error"]["code"], "player_not_found")
        self.assertEqual(self.c.get("/api/v1/nothing").status_code, 404)

    def test_player_detail_and_compare(self):
        d = self.c.get("/api/v1/batters/rankings?page_size=3").json["items"]
        ids = [i["player_id"] for i in d]
        det = self.c.get(f"/api/v1/players/{ids[0]}?role=bat").json["profiles"]["bat"]
        self.assertEqual(det["rank"], 1); self.assertIn("availability_note", det)
        cmp = self.c.get(f"/api/v1/players/compare?role=bat&ids={','.join(map(str, ids))}").json
        self.assertEqual([p["player_id"] for p in cmp["players"]], ids)

    def test_pressure_and_models_endpoints(self):
        cats = self.c.get("/api/v1/pressure/overview").json["categories"]
        self.assertEqual([c["category"] for c in cats], ["Low", "Moderate", "High", "Critical"])
        self.assertAlmostEqual(sum(c["share_pct"] for c in cats), 100, delta=0.1)
        m = self.c.get("/api/v1/models/metrics").json
        self.assertEqual(set(m["tasks"]), {"x_runs", "x_out", "x_charged", "x_bwk", "wp", "lev"})
        self.assertGreater(len(self.c.get("/api/v1/models/feature-importance?task=wp").json["items"]), 3)
        self.assertEqual(len(self.c.get("/api/v1/pressure/distribution").json["by_over"]), 40)
        self.assertIn("split_half", self.c.get("/api/v1/methodology/validation").json)

    def test_recommendations(self):
        r = self.c.get("/api/v1/scouting/recommendations?role=bowl&limit=5").json
        self.assertEqual(len(r["items"]), 5)
        top = self.c.get("/api/v1/bowlers/rankings?page_size=1").json["items"][0]["player_id"]
        like = self.c.get(f"/api/v1/scouting/recommendations?role=bowl&like={top}").json
        self.assertNotIn(top, [i["player_id"] for i in like["items"]])

    def test_exports_contain_only_aggregates(self):
        r = self.c.get("/api/v1/exports/rankings/bat.csv"); self.assertEqual(r.mimetype, "text/csv")
        cols = r.data.decode().splitlines()[0].split(",")
        self.assertNotIn("striker_id", cols); self.assertNotIn("innings_ball_num", cols)
        pid = self.c.get("/api/v1/batters/rankings?page_size=1").json["items"][0]["player_id"]
        pdf = self.c.get(f"/api/v1/scouting/report/bat/{pid}.pdf"); self.assertEqual(pdf.data[:4], b"%PDF")

    def test_every_json_endpoint_is_strict_json(self):
        import json
        def boom(c): raise ValueError(f"non-standard JSON constant {c}")
        paths = ["/overview", "/batters/rankings?status=all&page_size=200", "/bowlers/rankings?status=all&page_size=200", "/pressure/overview", "/pressure/distribution", "/models/metrics",
                 "/models/feature-importance?task=wp", "/methodology/validation", "/scouting/recommendations?role=bat", "/scouting/shortlist", "/scenario/presets",
                 "/scenario/simulate?innings=2&runs_required=45&balls_remaining=24&wickets_remaining=4&explain=1", "/players?q=a"]
        for p in paths:
            r = self.c.get("/api/v1" + p); self.assertEqual(r.status_code, 200, p)
            json.loads(r.data, parse_constant=boom)

    def test_rate_limit(self):
        c = make(rate_limit_per_min=5)
        codes = [c.get("/api/v1/health").status_code for _ in range(8)]
        self.assertEqual(codes[:5], [200] * 5); self.assertEqual(codes[-1], 429)


@unittest.skipUnless(HAVE, "run scripts/run_pipeline.py first")
class ShortlistAndAuth(unittest.TestCase):
    def setUp(self):
        self.c = make(); self.pid = self.c.get("/api/v1/batters/rankings?page_size=1").json["items"][0]["player_id"]

    def test_write_requires_key(self):
        self.assertEqual(self.c.post("/api/v1/scouting/shortlist", json={"player_id": self.pid, "role": "bat"}).status_code, 401)
        self.assertEqual(self.c.post("/api/v1/scouting/shortlist", json={"player_id": self.pid, "role": "bat"}, headers={"X-API-Key": "wrong"}).status_code, 401)
        self.assertEqual(self.c.get("/api/v1/admin/status").status_code, 401)

    def test_fail_closed_without_configured_key(self):
        c = create_app(load_settings(env="production", db_path=":memory:", api_key=None, serve_frontend=False)).test_client()
        self.assertEqual(c.post("/api/v1/scouting/shortlist", json={"player_id": self.pid, "role": "bat"}).status_code, 503)

    def test_full_shortlist_flow(self):
        r = self.c.post("/api/v1/scouting/shortlist", json={"player_id": self.pid, "role": "bat", "note": "watch vs spin"}, headers=KEY); self.assertEqual(r.status_code, 201)
        self.assertEqual(self.c.post("/api/v1/scouting/shortlist", json={"player_id": self.pid, "role": "bat"}, headers=KEY).status_code, 409)
        sl = self.c.get("/api/v1/scouting/shortlist").json
        self.assertEqual(sl["count"], 1); self.assertEqual(sl["items"][0]["note"], "watch vs spin"); self.assertIn("gaps", sl["balance"])
        self.assertEqual(self.c.patch(f"/api/v1/scouting/shortlist/{self.pid}?role=bat", json={"note": "updated"}, headers=KEY).json["note"], "updated")
        self.assertIn("updated", self.c.get("/api/v1/exports/shortlist.csv").data.decode())
        rec = self.c.get("/api/v1/scouting/recommendations?role=bat&limit=30").json["items"]
        self.assertNotIn(self.pid, [i["player_id"] for i in rec])          # shortlisted players are excluded from suggestions
        self.assertEqual(self.c.delete(f"/api/v1/scouting/shortlist/{self.pid}?role=bat", headers=KEY).status_code, 204)
        self.assertEqual(self.c.delete(f"/api/v1/scouting/shortlist/{self.pid}?role=bat", headers=KEY).status_code, 404)
        st = self.c.get("/api/v1/admin/status", headers=KEY).json
        self.assertEqual(st["audit_entries"], 3); self.assertIn("001_init.sql", st["migrations"])

    def test_input_validation(self):
        for body in ({"player_id": "1", "role": "bat"}, {"player_id": True, "role": "bat"}, {"player_id": self.pid, "role": "x"}, {"player_id": 1, "role": "bat", "note": "n" * 2001}):
            self.assertEqual(self.c.post("/api/v1/scouting/shortlist", json=body, headers=KEY).status_code, 400, body)
        self.assertEqual(self.c.post("/api/v1/scouting/shortlist", json={"player_id": 999999999, "role": "bat"}, headers=KEY).status_code, 404)
        self.assertEqual(self.c.post("/api/v1/scouting/shortlist", data="notjson", headers=KEY).status_code, 400)

    def test_sql_injection_is_inert(self):
        r = self.c.post("/api/v1/scouting/shortlist", json={"player_id": self.pid, "role": "bat", "note": "x'); DROP TABLE shortlist;--"}, headers=KEY)
        self.assertEqual(r.status_code, 201); self.assertEqual(self.c.get("/api/v1/scouting/shortlist").json["count"], 1)


class NoData(unittest.TestCase):
    def test_graceful_without_outputs(self):
        import tempfile
        c = create_app(load_settings(env="test", db_path=":memory:", processed_dir=Path(tempfile.mkdtemp()), serve_frontend=False)).test_client()
        self.assertEqual(c.get("/api/v1/health").status_code, 200)
        self.assertEqual(c.get("/api/v1/health/ready").status_code, 503)
        self.assertEqual(c.get("/api/v1/overview").json["error"]["code"], "analytics_unavailable")


if __name__ == "__main__":
    unittest.main()
