import * as api from '../api.js';
import { html, raw, n0, n1, frac } from '../util.js';
import { kpi, card, callout, tierBadge, evidenceNote } from '../components.js';
import { forest, lines } from '../charts.js';

export const meta = { path: 'overview', title: 'Command Centre', nav: 'Command Centre' };
export async function load() {
  const [overview, dist, bat, bowl] = await Promise.all([
    api.get('/overview'), 
    api.get('/pressure/distribution'), 
    api.get('/batters/rankings', { page_size: 10 }), 
    api.get('/bowlers/rankings', { page_size: 10 })
  ]);
  return { overview, dist, bat, bowl };
}
const fr = (items) => items.map((i) => ({ label: `${i.rank}. ${i.player}`, value: i.PRI, lo: i.PRI_lo, hi: i.PRI_hi }));

export function view({ overview: o, dist, bat, bowl }) {
  const series = [1, 2].map((inn) => ({ name: inn === 1 ? 'Setting (innings 1)' : 'Chasing (innings 2)', dash: inn === 2, points: dist.by_over.filter((r) => r.innings === inn).map((r) => ({ x: r.over, y: 100 * r.pressure_share })) }));
  const top = (t, label) => html`<div class="kpi"><div class="kpi-label">${label}</div><div class="kpi-value sm">${t.player}</div><div class="kpi-sub">PRI ${n1(t.PRI)} (${n1(t.PRI_lo)}–${n1(t.PRI_hi)}) · ${tierBadge(t.tier)}</div></div>`;
  
  return html`
  <section class="hero">
    <div>
      <p class="eyebrow">THE SCIENCE BEHIND THE SELECTION.</p>
      <h2 class="hero-title">Who can Rajasthan Royals rely on when the pressure rises?</h2>
      <p class="lead">PLAYBOOK 27 measures how batters and bowlers perform in high-leverage moments <em>compared with an average player in the same situation</em> — then shows how much that evidence can be trusted.</p>
      <p class="hero-links"><a class="btn primary" href="#/batters">Explore batters</a> <a class="btn" href="#/bowlers">Explore bowlers</a> <a class="btn ghost" href="#/about">How it works</a></p>
    </div>
    <ol class="how">
      <li><strong>Define pressure.</strong> A model estimates how much each ball can swing the match (leverage); the top 20% within each innings is “pressure”.</li>
      <li><strong>Compare to expectation.</strong> Every ball is scored against what an average player achieves in that exact situation.</li>
      <li><strong>Shrink &amp; test.</strong> Small samples are pulled toward average; rankings carry intervals, tiers and stability checks.</li>
    </ol>
  </section>
  
  ${callout('warn', 'Read the evidence strength', 'Validation found pressure performance is only weakly persistent across matches. Rankings below are the best available evidence from ~800 matches — not a guaranteed order.')}
  
  <div class="kpi-grid">
    ${kpi({ label: 'Players analysed', value: n0(o.players_analysed) })}
    ${kpi({ label: 'Matches analysed', value: n0(o.matches_analysed), sub: `${o.dataset_coverage.date_range[0]} → ${o.dataset_coverage.date_range[1]}` })}
    ${kpi({ label: 'Pressure deliveries', value: n0(o.pressure_deliveries), sub: `of ${n0(o.deliveries_analysed)} analysed` })}
    ${kpi({ label: 'Ranked batters', value: n0(o.eligible_batters), sub: `min ${n0(o.min_pressure_deliveries.bat)} pressure deliveries` })}
    ${kpi({ label: 'Ranked bowlers', value: n0(o.eligible_bowlers), sub: `min ${n0(o.min_pressure_deliveries.bowl)} pressure deliveries` })}
    ${top(o.top_batter, 'Top-rated batter')}
    ${top(o.top_bowler, 'Top-rated bowler')}
    ${kpi({ label: 'Model status', value: `v${o.model_status.model_version}`, sub: `pipeline ${o.model_status.pipeline_version} · run ${o.dataset_coverage.run_utc.slice(0, 10)}` })}
  </div>
  
  <div class="grid-2">
    ${card('Top 10 batters — Pressure Reliability Index', raw(forest(fr(bat.items), { label: 'Top 10 batters by PRI with 90% bootstrap intervals' })), { sub: 'Dot = PRI, bar = 90% interval. Overlapping bars mean the order is not reliable.' })}
    ${card('Top 10 bowlers — Pressure Reliability Index', raw(forest(fr(bowl.items), { label: 'Top 10 bowlers by PRI with 90% bootstrap intervals' })), { sub: 'Dot = PRI, bar = 90% interval.' })}
  </div>
  
  ${card('Where does pressure occur? Share of deliveries classed as pressure, by over', raw(lines(series, { label: 'Share of deliveries that are pressure, by over and innings', xLabel: 'over', yLabel: '% of deliveries', fmt: (v) => `${Math.round(v)}%`, yMin: 0 })), { sub: 'Pressure is contextual, not “death overs only”: it appears in the middle overs of both innings and from the powerplay in chases.' })}
  
  ${evidenceNote}
  
  ${card('Dataset coverage', html`<ul class="plain">
    <li>Competition mix (in-scope matches): ${Object.entries(o.dataset_coverage.tiers).map(([k, v]) => `${k} ${v}`).join(' · ')}</li>
    <li>Raw files: ${Object.entries(o.dataset_coverage.raw_row_counts).map(([k, v]) => `${k} ${n0(v)}`).join(' · ')} rows</li>
    <li>Roles are inferred from data; auction availability and prices are not in the dataset.</li>
  </ul>`)}
  `;
}
