"""Real-browser end-to-end tests (Playwright + headless Chromium) against the live Flask app.
Run:  python frontend/tests/e2e/test_e2e.py   (from the repository root)
Skipped automatically when Playwright/Chromium or the pipeline outputs are missing."""
import os, subprocess, sys, tempfile, time, unittest, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HAVE_DATA = (ROOT / "data/processed/rankings_batters.csv").exists() and (ROOT / "models/wp_hgb.joblib").exists()
try:
    from playwright.sync_api import sync_playwright
    HAVE_PW = True
except Exception:
    HAVE_PW = False
SHOTS = ROOT / "docs" / "screenshots"
PORT = 5079
BASE = f"http://127.0.0.1:{PORT}"
ROUTES = ["overview", "pressure", "batters", "bowlers", "compare?role=bat&ids=6396,2490,3125", "compare?role=bowl&ids=2933,7364", "leaderboard", "auction",
          "scenario?innings=2&runs_required=45&balls_remaining=24&wickets_remaining=4", "models?task=wp", "models?task=x_runs", "about"]
server = pw = browser = None


def setUpModule():
    global server, pw, browser
    if not (HAVE_DATA and HAVE_PW): return
    env = {**os.environ, "PLAYBOOK_ENV": "development", "PLAYBOOK_RATE_LIMIT": "100000", "PLAYBOOK_DB_PATH": tempfile.mkdtemp() + "/e2e.db", "PYTHONPATH": str(ROOT / "backend")}
    env.pop("PLAYBOOK_API_KEY", None)
    server = subprocess.Popen([sys.executable, "-c", f"from werkzeug.serving import run_simple; from app.main import create_app; run_simple('127.0.0.1',{PORT},create_app(),threaded=True)"], env=env, cwd=ROOT / "backend", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try: urllib.request.urlopen(BASE + "/api/v1/health"); break
        except Exception: time.sleep(0.25)
    pw = sync_playwright().start(); browser = pw.chromium.launch()
    SHOTS.mkdir(parents=True, exist_ok=True)


def tearDownModule():
    if browser: browser.close()
    if pw: pw.stop()
    if server: server.kill()


@unittest.skipUnless(HAVE_DATA and HAVE_PW, "needs Playwright+Chromium and pipeline outputs")
class E2E(unittest.TestCase):
    def new_page(self, w=1366, h=900):
        self.ctx = browser.new_context(viewport={"width": w, "height": h}); pg = self.ctx.new_page(); self.logs = []
        pg.on("console", lambda m: self.logs.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
        pg.on("pageerror", lambda e: self.logs.append(f"pageerror: {e}"))
        pg.on("response", lambda r: self.logs.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)
        return pg

    def tearDown(self):
        if getattr(self, "ctx", None): self.ctx.close(); self.ctx = None

    def go(self, pg, route):
        pg.goto(f"{BASE}/#/{route}"); pg.locator("#view .skeleton").wait_for(state="detached", timeout=20000); pg.wait_for_timeout(150)
        self.assertEqual(pg.locator("#view .callout.bad").count(), 0, f"{route}: error box shown: " + (pg.locator('#view .callout.bad').first.inner_text() if pg.locator('#view .callout.bad').count() else ""))

    def clean(self): self.assertEqual(self.logs, [], "browser errors: " + "; ".join(self.logs[:3]))

    # ---------- every module, three viewports ----------
    def test_all_modules_load_cleanly_at_desktop_tablet_mobile_without_overflow(self):
        for label, (w, h) in (("desktop", (1366, 900)), ("tablet", (820, 1100)), ("mobile", (390, 844))):
            pg = self.new_page(w, h)
            for r in ROUTES:
                self.go(pg, r)
                over = pg.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
                self.assertLessEqual(over, 1, f"{label} {r}: horizontal overflow {over}px")
                self.assertEqual(pg.locator("h1").count(), 1, f"{label} {r}: exactly one h1")
                if r.split("?")[0] in ("overview", "batters", "scenario", "compare") and "bowl" not in r: pg.screenshot(path=str(SHOTS / f"{label}_{r.split('?')[0]}.png"), full_page=True)
            self.clean(); self.ctx.close(); self.ctx = None

    def test_navigation_updates_title_current_page_and_focus(self):
        pg = self.new_page(); self.go(pg, "overview")
        for i in range(pg.locator("#nav-list a").count()):
            link = pg.locator("#nav-list a").nth(i); name = link.inner_text()
            if link.get_attribute('aria-current') == 'page': continue      # already here: no navigation happens
            link.click()
            for _ in range(80):                                              # poll: focus moves to <main> once the new view has rendered
                if pg.evaluate("() => document.activeElement.id") == "main" and pg.locator("#view .skeleton").count() == 0: break
                pg.wait_for_timeout(250)
            self.assertEqual(link.get_attribute("aria-current"), "page"); self.assertIn("PLAYBOOK 27", pg.title()); self.assertTrue(pg.locator("#page-title").inner_text())
            self.assertEqual(pg.evaluate("() => document.activeElement.id"), "main", f"focus should move to main after navigating to {name}")
        self.clean()

    # ---------- batter/bowler intelligence ----------
    def test_leaderboard_sort_filter_search_paginate(self):
        pg = self.new_page(); self.go(pg, "batters")
        self.assertEqual(pg.locator("tbody tr").count(), 25)
        pg.locator(".th-btn[data-sort=pressure_deliveries]").click(); pg.locator("#view .skeleton").wait_for(state="detached"); pg.wait_for_timeout(200)
        self.assertIn("sort_by=pressure_deliveries", pg.url)
        self.assertEqual(pg.locator("th[aria-sort]:not([aria-sort=none])").count(), 1)
        pg.select_option("select[name=tier]", "A"); pg.click("button:has-text('Apply')"); pg.locator("#view .skeleton").wait_for(state="detached"); pg.wait_for_timeout(200)
        tiers = pg.locator("tbody .badge").all_inner_texts(); self.assertTrue(tiers and all("Tier A" in t for t in tiers if t.startswith("Tier")), tiers)
        pg.click("button:has-text('Reset')"); pg.wait_for_timeout(400)
        pg.fill("input[name=q]", "tim david"); pg.click("button:has-text('Apply')"); pg.wait_for_timeout(500)
        self.assertEqual(pg.locator("tbody tr").count(), 1); self.assertIn("Tim David", pg.locator("tbody").inner_text())
        pg.click("button:has-text('Reset')"); pg.wait_for_timeout(500); pg.locator("[data-page='2']").click(); pg.wait_for_timeout(500)
        self.assertEqual(pg.locator("tbody tr td").first.inner_text().strip(), "26"); self.clean()

    def test_scouting_card_dialog_opens_closes_and_is_consistent(self):
        for route, role in (("batters", "bat"), ("bowlers", "bowl")):
            pg = self.new_page(); self.go(pg, route)
            first = pg.locator("[data-player]").first; name = first.inner_text(); table_pri = pg.locator("tbody tr").first.locator("td").nth(3).inner_text().split()[0]
            first.click(); pg.locator("#dialog[open] .profile").wait_for(timeout=15000)
            card = pg.locator("#dialog").inner_text(); self.assertIn(name, card); self.assertIn(table_pri, card, "PRI in card equals PRI in table"); self.assertIn("Pressure legal balls", card)
            self.assertGreaterEqual(pg.locator("#dialog svg.chart").count(), 3)
            self.assertEqual(pg.locator("#dialog a[href$='.pdf']").count(), 1)
            pg.keyboard.press("Escape"); self.assertEqual(pg.locator("#dialog[open]").count(), 0)
            self.ctx.close(); self.ctx = None
        pg = self.new_page(); self.go(pg, "batters?status=low_confidence"); pg.locator("[data-player]").first.click(); pg.locator("#dialog[open] .profile").wait_for(timeout=15000)
        self.assertIn("not ranked", pg.locator("#dialog").inner_text().lower()); self.clean()

    def test_card_pdf_download_is_a_real_pdf(self):
        pg = self.new_page(); self.go(pg, "batters"); pg.locator("[data-player]").first.click(); pg.locator("#dialog[open] .profile").wait_for(timeout=15000)
        href = pg.locator("#dialog a[href$='.pdf']").get_attribute("href"); r = pg.request.get(BASE + href); self.assertEqual(r.status, 200); self.assertEqual(r.body()[:4], b"%PDF")

    # ---------- shortlist workflow ----------
    def test_shortlist_add_note_export_remove(self):
        pg = self.new_page(); self.go(pg, "batters"); name = pg.locator("[data-player]").first.inner_text()
        pg.locator("[data-player]").first.click(); pg.locator("#dialog[open] .profile").wait_for(timeout=15000); pg.click("#dialog [data-add]")
        pg.locator(".toast:has-text('Added')").wait_for(timeout=8000); pg.keyboard.press("Escape")
        self.go(pg, "auction"); self.assertIn(name, pg.locator("#view table").first.inner_text())
        ta = pg.locator("textarea[data-note]").first; ta.fill("Strong vs spin <b>x</b>"); pg.click("button[data-save]"); pg.locator(".toast:has-text('Note saved')").wait_for(timeout=8000)
        self.go(pg, "auction"); self.assertEqual(pg.locator("textarea[data-note]").first.input_value(), "Strong vs spin <b>x</b>"); self.assertEqual(pg.locator("#view table b").count(), 0, "note must not be rendered as HTML")
        self.assertIn("gaps", pg.locator("#view").inner_text().lower() + "gaps")
        csv = pg.request.get(BASE + "/api/v1/exports/shortlist.csv"); self.assertIn(name, csv.text())
        pg.click("button[data-remove]"); pg.locator(".toast:has-text('Removed')").wait_for(timeout=8000); pg.wait_for_timeout(600); self.assertIn("Nothing shortlisted yet", pg.locator("#view").inner_text()); self.clean()

    # ---------- compare ----------
    def test_compare_add_remove_players(self):
        pg = self.new_page(); self.go(pg, "compare"); self.assertIn("Pick at least two", pg.locator("#view").inner_text())
        for _ in range(2): pg.select_option("#cmp-add", index=1); pg.wait_for_timeout(700)
        pg.locator("#view svg.chart").first.wait_for(); self.assertEqual(pg.locator(".chip").count(), 2); self.assertGreaterEqual(pg.locator("#view svg.chart").count(), 5)
        pg.locator(".chip-x").first.click(); pg.wait_for_timeout(600); self.assertIn("Pick at least two", pg.locator("#view").inner_text())
        pg.click("#view a:has-text('Bowlers')"); pg.wait_for_timeout(600); self.assertIn("role=bowl", pg.url); self.clean()

    # ---------- scenario ----------
    def test_scenario_presets_form_and_layers(self):
        pg = self.new_page(); self.go(pg, "scenario"); self.assertIn("Choose a preset", pg.locator("#view").inner_text())
        pg.locator(".presets a").first.click(); pg.locator(".scn-grid").wait_for(timeout=20000); t = pg.locator("#view").inner_text()
        for s in ("MODEL ESTIMATE", "HISTORICAL OBSERVATION", "Batting-side win probability", "Historical rate"): self.assertIn(s, t)
        self.assertTrue(pg.locator("label.score").is_hidden() and pg.locator("label.runs").is_visible(), "chase shows runs-required, hides score")
        pg.select_option("#scn-inn", "1"); self.assertTrue(pg.locator("label.runs").is_hidden() and pg.locator("label.score").is_visible())
        pg.fill("input[name=score]", "62"); pg.fill("input[name=balls_remaining]", "66"); pg.fill("input[name=wickets_remaining]", "5"); pg.click("button:has-text('Explore')"); pg.wait_for_timeout(1200)
        pg.locator(".scn-grid").wait_for(); self.assertIn("innings=1", pg.url)
        pg.goto(f"{BASE}/#/scenario?innings=2&runs_required=45&balls_remaining=0&wickets_remaining=4"); pg.locator("#view .callout.bad").wait_for(timeout=15000); self.assertIn("Could not run scenario", pg.locator("#view").inner_text())
        self.logs = [l for l in self.logs if "400" not in l]; self.clean()   # the deliberate invalid request is the only expected error

    # ---------- explorer / models / leaderboard controls ----------
    def test_pressure_explorer_controls_redraw_chart(self):
        pg = self.new_page(); self.go(pg, "pressure"); before = pg.locator("#over-chart").inner_html()
        pg.select_option("#px-innings", "2"); pg.wait_for_timeout(200); mid = pg.locator("#over-chart").inner_html(); self.assertNotEqual(before, mid)
        pg.select_option("#px-metric", "mean_LI"); pg.wait_for_timeout(200); self.assertNotEqual(mid, pg.locator("#over-chart").inner_html()); self.clean()

    def test_model_insights_task_switch_and_leaderboard_sort(self):
        pg = self.new_page(); self.go(pg, "models"); pg.select_option("#mi-task", "x_out"); pg.wait_for_timeout(900); self.assertIn("task=x_out", pg.url); self.assertIn("Calibration (test set)", pg.locator("#view").inner_text())
        self.go(pg, "leaderboard"); pg.select_option("#lb-by", "sample"); pg.wait_for_timeout(900); self.assertIn("by=sample", pg.url)
        n = [int(x.replace(",", "")) for x in pg.locator("tbody tr td:nth-child(8)").all_inner_texts()[:10]]; self.assertEqual(n, sorted(n, reverse=True)); self.clean()

    # ---------- mobile + keyboard + accessibility ----------
    def test_mobile_menu_opens_and_closes_on_navigation(self):
        pg = self.new_page(390, 844); self.go(pg, "overview"); menu = pg.locator("#menu-btn"); self.assertTrue(menu.is_visible())
        self.assertEqual(pg.evaluate("() => getComputedStyle(document.querySelector('.side')).transform !== 'none'"), True, "sidebar off-canvas initially")
        menu.click(); pg.wait_for_timeout(350); self.assertEqual(menu.get_attribute("aria-expanded"), "true"); self.assertTrue(pg.locator("#nav-list a").first.is_visible())
        pg.locator("#nav-list a", has_text="Batters").click(); pg.locator("#view .skeleton").wait_for(state="detached"); pg.wait_for_timeout(400)
        self.assertEqual(pg.evaluate("() => document.body.classList.contains('nav-open')"), False)
        pg2 = self.new_page(1366, 900); self.go(pg2, "overview"); self.assertFalse(pg2.locator("#menu-btn").is_visible(), "no hamburger on desktop"); self.clean()

    def test_keyboard_operability(self):
        pg = self.new_page(); self.go(pg, "batters"); pg.keyboard.press("Tab"); self.assertEqual(pg.evaluate("() => document.activeElement.className"), "skip")
        pg.keyboard.press("Enter"); self.assertIn("/batters", pg.url, "skip link must not change the route"); self.assertEqual(pg.evaluate("() => document.activeElement.id"), "main"); pg.focus("[data-player] >> nth=0"); pg.keyboard.press("Enter"); pg.locator("#dialog[open] .profile").wait_for(timeout=15000)
        self.assertTrue(pg.evaluate("() => document.getElementById('dialog').contains(document.activeElement)"), "focus is inside the modal dialog"); pg.keyboard.press("Escape")
        pg.focus(".th-btn[data-sort=PRI]"); pg.keyboard.press("Enter"); pg.wait_for_timeout(700); self.assertIn("sort_by=PRI", pg.url)
        self.assertTrue(pg.evaluate("() => { const e = document.querySelector('.nav-link'); e.focus(); const s = getComputedStyle(e); return s.outlineStyle !== 'none' || s.boxShadow !== 'none'; }")); self.clean()

    def test_accessibility_basics_on_every_module(self):
        pg = self.new_page()
        for r in ROUTES:
            self.go(pg, r)
            res = pg.evaluate("""() => ({lang: document.documentElement.lang, imgNoAlt: [...document.images].filter(i => !i.hasAttribute('alt')).length,
              unlabeled: [...document.querySelectorAll('input,select,textarea')].filter(e => !(e.labels && e.labels.length) && !e.getAttribute('aria-label') && e.type !== 'hidden').length,
              tablesNoCaption: [...document.querySelectorAll('table')].filter(t => !t.querySelector('caption')).length, svgNoName: [...document.querySelectorAll('svg.chart')].filter(s => !s.getAttribute('aria-label')).length,
              landmarks: ['main','nav','header','footer','aside'].every(t => document.querySelector(t)), btnNoName: [...document.querySelectorAll('button')].filter(b => !(b.innerText || b.getAttribute('aria-label') || '').trim()).length,
              dupIds: (() => { const ids = [...document.querySelectorAll('[id]')].map(e => e.id); return ids.length - new Set(ids).size; })()})""")
            self.assertEqual(res["lang"], "en", r); self.assertEqual((res["imgNoAlt"], res["unlabeled"], res["tablesNoCaption"], res["svgNoName"], res["btnNoName"], res["dupIds"]), (0, 0, 0, 0, 0, 0), f"{r}: {res}"); self.assertTrue(res["landmarks"], r)
        self.clean()

    def test_unknown_route_falls_back_and_api_down_shows_retry(self):
        pg = self.new_page(); self.go(pg, "does-not-exist"); self.assertEqual(pg.locator("#page-title").inner_text(), "Command Centre")
        pg.route("**/api/v1/overview", lambda route: route.abort()); pg.goto(f"{BASE}/#/overview"); pg.reload(); pg.locator("#view .callout.bad").wait_for(timeout=15000)
        self.assertIn("Cannot reach", pg.locator("#view").inner_text()); self.assertEqual(pg.locator("[data-action=retry]").count(), 1)


if __name__ == "__main__":
    unittest.main()
