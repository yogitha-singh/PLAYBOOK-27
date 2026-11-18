"""Static contract between the JavaScript UI and the Flask backend (no browser needed)."""
import re, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.analytics import config as acfg
from app.core.config import load_settings
from app.main import create_app

FE = acfg.ROOT / "frontend"
app = create_app(load_settings(env="test", db_path=":memory:", serve_frontend=True))
JS = sorted(FE.glob("js/**/*.js"))


def api_calls():
    out = []
    for f in JS:
        t = f.read_text(encoding="utf-8")
        for m in re.finditer(r"""(?:api\.(get|write|url)\(\s*(?:'(?:GET|POST|PATCH|DELETE)',\s*)?|get\(\s*)(['"`])(/[^'"`]*)\2""", t):
            kind, path = m.group(1), m.group(3)
            method = "GET"
            w = re.match(r"api\.write\(\s*'(\w+)'", t[m.start():])
            if w: method = w.group(1)
            out.append((f.name, method, re.sub(r"\$\{[^}]*\}", "1", path.split("?")[0])))
    return out


class Contract(unittest.TestCase):
    def test_every_ui_api_call_matches_a_backend_route(self):
        adapter = app.url_map.bind("localhost")
        calls = api_calls(); self.assertGreater(len(calls), 20)
        for fname, method, path in calls:
            full = "/api/v1" + path
            # .pdf/.csv template paths contain placeholders handled by converters
            try: adapter.match(full, method=method)
            except Exception as e: self.fail(f"{fname}: {method} {full} has no backend route ({type(e).__name__})")

    def test_frontend_files_are_served_with_correct_types(self):
        c = app.test_client()
        r = c.get("/"); self.assertEqual(r.status_code, 200); self.assertIn(b"PLAYBOOK 27", r.data)
        html = r.data.decode()
        refs = re.findall(r'(?:src|href)="([^"#]+)"', html)
        for ref in refs:
            if ref.startswith(("http", "#")): continue
            resp = c.get("/" + ref); self.assertEqual(resp.status_code, 200, ref)
        self.assertIn("javascript", c.get("/js/app.js").mimetype); self.assertEqual(c.get("/css/app.css").mimetype, "text/css"); self.assertEqual(c.get("/assets/logo.svg").mimetype, "image/svg+xml")
        self.assertEqual(c.get("/api/v1/nothing").status_code, 404)

    def test_every_js_import_resolves(self):
        for f in JS:
            for m in re.finditer(r"""from\s+['"](\.[^'"]+)['"]""", f.read_text(encoding="utf-8")):
                self.assertTrue((f.parent / m.group(1)).resolve().exists(), f"{f.name} imports missing {m.group(1)}")

    def test_csp_compatible_no_inline_script_or_handlers(self):
        idx = (FE / "index.html").read_text()
        self.assertEqual(len(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", idx)), 0)
        for f in [FE / "index.html", *JS]:
            self.assertIsNone(re.search(r"\son(click|load|error|change|submit)\s*=", f.read_text(encoding="utf-8")), f.name)
        r = app.test_client().get("/"); self.assertIn("script-src 'self'", r.headers["Content-Security-Policy"])

    def test_no_secrets_or_hardcoded_hosts_in_frontend(self):
        for f in JS:
            t = f.read_text(encoding="utf-8"); self.assertNotRegex(t, r"https?://(?!www\.w3\.org)", f.name); self.assertNotRegex(t, r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9]{8,}", f.name)


if __name__ == "__main__":
    unittest.main()
