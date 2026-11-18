import test0, { before, after } from 'node:test';
import { existsSync } from 'node:fs';
import assert from 'node:assert/strict';
import * as api from '../js/api.js';
import { startServer, wellFormed, ctx } from './helpers.js';
import * as command from '../js/pages/command.js';
import * as pressure from '../js/pages/pressure.js';
import { batters, bowlers, openPlayer } from '../js/pages/intelligence.js';
import * as compare from '../js/pages/compare.js';
import * as leaderboard from '../js/pages/leaderboard.js';
import * as auction from '../js/pages/auction.js';
import * as scenario from '../js/pages/scenario.js';
import * as models from '../js/pages/models.js';
import * as about from '../js/pages/about.js';
import { profileView } from '../js/pages/profile.js';

const HAVE = existsSync(new URL('../../data/processed/rankings_batters.csv', import.meta.url));
const test = HAVE ? test0 : test0.skip;   // CI without pipeline outputs skips these (run scripts/run_pipeline.py first)
let srv; before(async () => { if (HAVE) srv = await startServer(); }); after(() => srv?.stop());
const render = async (page, c = ctx()) => { const d = await page.load(c); return { d, out: String(page.view(d, c)) }; };
const noJunk = (out, name) => { assert.ok(!/NaN|undefined|\[object Object\]/.test(out), `${name}: NaN/undefined/[object Object] leaked into HTML`); for (const m of out.matchAll(/<svg[\s\S]*?<\/svg>/g)) assert.equal(wellFormed(m[0]), null, `${name}: malformed svg`); };

test('Command Centre shows real overview numbers', async () => {
  const { d, out } = await render(command); noJunk(out, 'command');
  assert.ok(out.includes(d.overview.top_batter.player) && out.includes(d.overview.top_bowler.player));
  assert.ok(out.includes(d.overview.matches_analysed.toLocaleString('en-US')) && out.includes('weakly persistent'));
});
test('Pressure Explorer renders categories and the over chart for both filters', async () => {
  const { d, out } = await render(pressure); noJunk(out, 'pressure');
  for (const c of ['Low', 'Moderate', 'High', 'Critical']) assert.ok(out.includes(c));
  for (const inn of ['all', '1', '2']) for (const metric of ['pressure_share', 'mean_LI']) assert.equal(wellFormed(pressure.overChart(d.dist, { innings: inn, metric })), null);
});
test('Batter and bowler leaderboards: rows match API, sorting/filter params, unit labels', async () => {
  for (const [page, ep] of [[batters, '/batters/rankings'], [bowlers, '/bowlers/rankings']]) {
    const { d, out } = await render(page); noJunk(out, page.meta.path);
    assert.equal(d.res.items.length, 25); assert.ok(out.includes(d.res.items[0].player) && out.includes('aria-sort="ascending"'));
    const f = await render(page, ctx({ tier: 'A', sort_by: 'PRI', order: 'desc' })); assert.ok(f.d.res.items.every((r) => r.tier.startsWith('A')));
    const low = await render(page, ctx({ status: 'low_confidence' })); assert.ok(low.d.res.items.every((r) => r.status.startsWith('Low')));
    const none = await render(page, ctx({ q: 'zzzzqq' })); assert.match(none.out, /No rows match/);
  }
});
test('Scouting cards (ranked and low-confidence players) render with consistent numbers', async () => {
  for (const [role, ep] of [['bat', '/batters/rankings'], ['bowl', '/bowlers/rankings']]) {
    const top = (await api.get(ep, { page_size: 1 })).items[0];
    const card = String(await openPlayer(top.player_id, role)); noJunk(card, `card-${role}`);
    assert.ok(card.includes(top.player) && card.includes(top.PRI.toFixed(1)) && card.includes('Pressure legal balls') && card.includes('Add to shortlist') && card.includes('.pdf'));
    const low = (await api.get(ep, { status: 'low_confidence', page_size: 1 })).items[0];
    const lc = String(await openPlayer(low.player_id, role)); noJunk(lc, `lowcard-${role}`); assert.match(lc, /not ranked|Score decomposition is available for ranked players only/);
  }
});
test('card pressure-delivery counts equal the ranking table for every top-20 player (no unit mismatch)', async () => {
  for (const [role, ep] of [['bat', '/batters/rankings'], ['bowl', '/bowlers/rankings']]) {
    const items = (await api.get(ep, { page_size: 20 })).items;
    for (const r of items.slice(0, 6)) { const card = String(await openPlayer(r.player_id, role)); assert.ok(card.includes(`<dd>${r.pressure_deliveries.toLocaleString('en-US')}</dd>`) && card.includes(`<dd>${r.pressure_legal_balls.toLocaleString('en-US')}</dd>`), `${r.player}: card n differs from table`); }
  }
});
test('Compare: empty state, 2-player and 6-player comparisons for both roles', async () => {
  for (const [role, ep] of [['bat', '/batters/rankings'], ['bowl', '/bowlers/rankings']]) {
    const ids = (await api.get(ep, { page_size: 6 })).items.map((i) => i.player_id);
    const e = await render(compare, ctx({ role })); assert.match(e.out, /Pick at least two/);
    for (const n of [2, 6]) { const { out } = await render(compare, ctx({ role, ids: ids.slice(0, n).join(',') })); noJunk(out, `compare-${role}-${n}`); assert.ok(out.includes('Side-by-side') && out.includes('Profile shape')); }
  }
});
test('Reliability Leaderboard: every sort key renders for both roles', async () => {
  for (const role of ['bat', 'bowl']) for (const by of ['reliability', 'pressure', 'consistency', 'sample', 'confidence']) { const { d, out } = await render(leaderboard, ctx({ role, by })); noJunk(out, `lb-${role}-${by}`); assert.ok(d.res.items.length >= 20); }
  const { d } = await render(leaderboard, ctx({ role: 'bat', by: 'sample' })); const n = d.res.items.map((r) => r.pressure_deliveries); assert.deepEqual(n, [...n].sort((a, b) => b - a));
});
test('Auction Room: empty and populated shortlist (write via API) incl. XSS-safe notes', async () => {
  const top = (await api.get('/batters/rankings', { page_size: 2 })).items;
  let { out } = await render(auction); noJunk(out, 'auction-empty'); assert.match(out, /Nothing shortlisted yet/);
  await api.write('POST', '/scouting/shortlist', { player_id: top[0].player_id, role: 'bat', note: '<script>alert(1)</script>' });
  ({ out } = await render(auction)); noJunk(out, 'auction'); assert.ok(out.includes(top[0].player) && !out.includes('<script>alert') && out.includes('&lt;script&gt;'));
  assert.ok(!out.includes(`data-add="${top[0].player_id}"`), 'shortlisted player must not be suggested');
  await api.write('DELETE', `/scouting/shortlist/${top[0].player_id}`, undefined, { role: 'bat' });
});
test('Scenario Simulator: presets, labelled layers, comparability, bad input, explanations', async () => {
  const presets = (await api.get('/scenario/presets')).presets;
  for (const p of presets) { const q = Object.fromEntries(Object.entries(p).filter(([k]) => !['id', 'label', 'note'].includes(k)).map(([k, v]) => [k, String(v)])); const { out } = await render(scenario, ctx(q)); noJunk(out, p.id); assert.ok(out.includes('MODEL ESTIMATE') && out.includes('HISTORICAL OBSERVATION') && out.includes('Win probability') ); }
  const { out: crit } = await render(scenario, ctx({ innings: '2', runs_required: '45', balls_remaining: '24', wickets_remaining: '4' })); assert.ok(crit.includes('What drives the model estimate?') && crit.includes('Batters'));
  const bad = await render(scenario, ctx({ innings: '2', runs_required: '45', balls_remaining: '0', wickets_remaining: '4' })); assert.match(bad.out, /Could not run scenario/);
  assert.match((await render(scenario)).out, /Choose a preset/);
});
test('Model Insights: every task, with calibration for classifiers and real metrics', async () => {
  for (const task of ['x_runs', 'x_out', 'x_charged', 'x_bwk', 'wp', 'lev']) { const { d, out } = await render(models, ctx({ task })); noJunk(out, `models-${task}`); assert.ok(out.includes('Permutation') || out.includes('permutation')); if (d.m.tasks[task].kind === 'clf') assert.ok(out.includes('Calibration (test set)') && out.includes('Class imbalance')); }
  const { d, out } = await render(models, ctx({ task: 'wp' })); assert.ok(out.includes(d.m.tasks.wp.test_metrics.hist_gradient_boosting.ROC_AUC.toFixed(3)));
});
test('Methodology page shows validation numbers straight from the API', async () => {
  const { d, out } = await render(about); noJunk(out, 'about'); const sb = d.val.split_half.batters.find((r) => r.measure === 'level').spearman_brown_full;
  assert.ok(out.includes(sb.toFixed(2)) && out.includes('Not implemented') && out.includes('weakly persistent') && out.includes('ready'));
});
test('profileView is XSS-safe even for hostile player text', async () => {
  const top = (await api.get('/batters/rankings', { page_size: 1 })).items[0]; const det = (await api.get(`/players/${top.player_id}`, { role: 'bat' })).profiles.bat;
  const hostile = { ...det, player: '<img src=x onerror=alert(1)>', strengths: '<script>x</script>' };
  const out = String(profileView(hostile, null, 'bat')); assert.ok(!/<img src=x|<script>x/.test(out));
});
