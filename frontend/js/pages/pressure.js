import * as api from '../api.js';
import { html, raw, n0, n1, n2, pct1 } from '../util.js';
import { card, callout, table } from '../components.js';
import { lines, grouped, stacked } from '../charts.js';

export const meta = { path: 'pressure', title: 'Pressure Explorer', nav: 'Pressure Explorer' };
export async function load() { const [ov, dist] = await Promise.all([api.get('/pressure/overview'), api.get('/pressure/distribution')]); return { ov, dist }; }
const METRICS = { pressure_share: ['% of deliveries classed as pressure', (v) => `${v.toFixed(0)}%`, 100], mean_LI: ['mean Leverage Index (1.0 = average ball)', (v) => v.toFixed(2), 1] };
export function overChart(dist, { innings = 'all', metric = 'pressure_share' } = {}) {
  const [lab, fmt, mult] = METRICS[metric] || METRICS.pressure_share;
  const inns = innings === 'all' ? [1, 2] : [Number(innings)];
  return lines(inns.map((i) => ({ name: i === 1 ? 'Setting (innings 1)' : 'Chasing (innings 2)', dash: i === 2, points: dist.by_over.filter((r) => r.innings === i).map((r) => ({ x: r.over, y: r[metric] * mult })) })),
    { label: `${lab} by over`, xLabel: 'over', yLabel: lab.split(' (')[0], fmt, yMin: 0 });
}
export function view({ ov, dist }, state = { innings: 'all', metric: 'pressure_share' }) {
  const cats = ov.categories, names = cats.map((c) => c.category), th = ov.thresholds.LI_thresholds;
  const mix = Object.fromEntries(dist.phase_mix_pct.map((r) => [r.phase, r]));
  return html`<p class="lead">${ov.definition}. Pressure is judged from <em>pre-delivery</em> information only (balls left, wickets in hand, score/required rate, venue par, team strength), so it never peeks at what happens next.</p>
  <div class="grid-2">${card('Do the categories really separate pressure from ordinary play?', raw(grouped(names, [{ name: 'Dismissal %', values: cats.map((c) => c.dismissal_pct) }, { name: 'Dot ball %', values: cats.map((c) => c.dot_pct) }, { name: 'Boundary %', values: cats.map((c) => c.boundary_pct) }], { label: 'Outcome rates by pressure category', fmt: (v) => `${v.toFixed(0)}%` })), { sub: 'Outcomes were NOT used to define pressure. Dismissals jump in Critical; dots fall as batters are forced to score.' })}
  ${card('Phase mix of each category', raw(stacked(names.map((c) => ({ label: c, parts: ['Powerplay', 'Middle', 'Death'].map((p) => ({ name: p, value: mix[p][c] })) })), { label: 'Share of each pressure category by innings phase' })), { sub: 'Percent of deliveries in each category that fall in each phase. High pressure is mostly middle overs; Critical is mostly death overs.' })}</div>
  ${card('Pressure by over', html`<div class="controls"><label>Innings <select id="px-innings"><option value="all">Both</option><option value="1"${state.innings === '1' ? raw(' selected') : ''}>Setting</option><option value="2"${state.innings === '2' ? raw(' selected') : ''}>Chasing</option></select></label>
  <label>Metric <select id="px-metric"><option value="pressure_share">Pressure share</option><option value="mean_LI"${state.metric === 'mean_LI' ? raw(' selected') : ''}>Mean leverage</option></select></label></div><div id="over-chart">${raw(overChart(dist, state))}</div>`)}
  ${card('Category profile', table({ caption: 'Pressure categories: counts and situational profile', rows: cats, columns: [
    { key: 'category', label: 'Category' }, { label: 'Deliveries', num: true, render: (r) => n0(r.deliveries) }, { label: 'Share', num: true, render: (r) => pct1(r.share_pct) }, { label: 'Avg wkts left', num: true, render: (r) => n1(r.mean_wkts_rem) },
    { label: 'Avg balls left', num: true, render: (r) => n0(r.mean_balls_rem) }, { label: 'Chase RRR', num: true, render: (r) => n1(r.chase_mean_rrr) }, { label: '% chase', num: true, render: (r) => pct1(r.pct_chase) }, { label: 'Runs/ball', num: true, render: (r) => n2(r.runs_per_ball) },
    { label: 'Dismissal %', num: true, render: (r) => pct1(r.dismissal_pct) }] }), { sub: 'Thresholds are quantiles of the Leverage Index within each innings.' })}
  <div class="grid-2">${card('Thresholds (Leverage Index)', table({ caption: 'Leverage Index quantile thresholds', rows: Object.entries(th).map(([k, v]) => ({ k: k.replace('_', ' '), ...v })), columns: [{ key: 'k', label: 'Innings' }, { label: 'P50 Low→Moderate', num: true, render: (r) => n2(r.P50) }, { label: 'P80 →High', num: true, render: (r) => n2(r.P80) }, { label: 'P95 →Critical', num: true, render: (r) => n2(r.P95) }] }))}
  ${callout('info', 'Limitations', ov.caveat + '. Leverage is model-estimated from ~800 matches; first-innings pressure is concentrated late in the innings and around collapses.')}</div>`;
}
export function mount(root, data) {
  const st = { innings: 'all', metric: 'pressure_share' };
  const redraw = () => { root.querySelector('#over-chart').innerHTML = overChart(data.dist, st); };
  root.querySelector('#px-innings')?.addEventListener('change', (e) => { st.innings = e.target.value; redraw(); });
  root.querySelector('#px-metric')?.addEventListener('change', (e) => { st.metric = e.target.value; redraw(); });
}
