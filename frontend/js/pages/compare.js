import * as api from '../api.js';
import { html, raw, n0, n1, n2, frac, pct1, isNum } from '../util.js';
import { card, table, tierBadge, confBadge, empty, callout } from '../components.js';
import { radar, grouped, forest } from '../charts.js';

export const meta = { path: 'compare', title: 'Player Comparison', nav: 'Player Comparison' };
export async function load(ctx) {
  const role = ctx.query.role === 'bowl' ? 'bowl' : 'bat';
  const ids = (ctx.query.ids || '').split(',').map(Number).filter(Boolean).slice(0, 6);
  const pool = await api.get(role === 'bat' ? '/batters/rankings' : '/bowlers/rankings', { page_size: 200 });
  const cmp = ids.length >= 2 ? await api.get('/players/compare', { role, ids: ids.join(',') }) : null;
  return { role, ids, pool: pool.items, cmp };
}
const AXES = [['PRI', 'PRI'], ['level100', 'Level'], ['consistency_pct', 'Consistency'], ['pressure_deliveries', 'Sample'], ['p_top10', 'P(top 10)'], ['share_top10', 'Stability']];
export function radarData(players, pool) {
  const rng = AXES.map(([k]) => { const v = pool.map((p) => p[k]).filter(isNum); return [Math.min(...v), Math.max(...v)]; });
  return { axes: AXES.map((a) => a[1]), series: players.map((p) => ({ name: p.player, values: AXES.map(([k], i) => (rng[i][1] === rng[i][0] ? 0.5 : (p[k] - rng[i][0]) / (rng[i][1] - rng[i][0]))) })) };
}
export function view({ role, ids, pool, cmp }) {
  const bat = role === 'bat';
  const sel = ids.map((i) => pool.find((p) => p.player_id === i)).filter(Boolean);
  const options = pool.filter((p) => !ids.includes(p.player_id)).map((p) => html`<option value="${p.player_id}">${p.rank}. ${p.player}</option>`);
  let results = empty('Pick at least two players to compare. Ranked players only; up to six.');
  if (cmp) {
    const P = cmp.players, names = P.map((p) => p.player), rd = radarData(P, pool);
    const a = bat ? { cats: ['Pressure SR', 'Other SR'], v: [(p) => p.p_strike_rate, (p) => p.b_strike_rate], t: 'Strike rate: pressure vs other' } : { cats: ['Pressure econ', 'Other econ'], v: [(p) => p.p_economy, (p) => p.b_economy], t: 'Economy: pressure vs other (lower is better)' };
    results = html`<div class="grid-2">${card('Reliability (PRI with 90% interval)', raw(forest(P.map((p) => ({ label: p.player, value: p.PRI, lo: p.PRI_lo, hi: p.PRI_hi })), { label: 'PRI with 90% intervals for the selected players' })), { sub: cmp.note })}
    ${card('Profile shape (minâ€“max within ranked pool)', raw(radar(rd.axes, rd.series, { label: 'Radar comparison across six evidence axes' })), { sub: 'Radar is one view only; compare the bars and table too.' })}</div>
    <div class="grid-2">${card(a.t, raw(grouped(names, [{ name: a.cats[0], values: P.map(a.v[0]) }, { name: a.cats[1], values: P.map(a.v[1]) }], { label: a.t })))}
    ${card(bat ? 'Expected vs actual under pressure' : 'Expected vs actual under pressure', raw(grouped(names, bat ? [{ name: 'Runs above exp.', values: P.map((p) => p.p_runs_above_exp) }, { name: 'Dismissals below exp.', values: P.map((p) => p.p_dismissals_below_exp) }] : [{ name: 'Runs saved vs exp.', values: P.map((p) => p.p_runs_saved_vs_exp) }, { name: 'Wickets above exp.', values: P.map((p) => p.p_wkts_above_exp) }], { label: 'Expected versus actual' })))}</div>
    ${card('Phase-specific performance', raw(grouped(['Powerplay', 'Middle', 'Death'], P.map((p) => ({ name: p.player, values: bat ? [p.sr_powerplay, p.sr_middle, p.sr_death] : [p.econ_powerplay, p.econ_middle, p.econ_death] })), { label: bat ? 'Strike rate by phase' : 'Economy by phase' })), { sub: `${bat ? 'Strike rate' : 'Economy'} by phase (â‰¥30 balls; gaps mean too few balls)` })}
    ${card('Side-by-side', table({ caption: 'Player comparison table', rows: P, columns: [{ key: 'player', label: 'Player' }, { label: 'Tier', render: (r) => tierBadge(r.tier) }, { label: 'PRI', num: true, render: (r) => n1(r.PRI) }, { label: 'Rank range', num: true, render: (r) => `${r.rank_lo}â€“${r.rank_hi}` }, { label: 'Value/100', num: true, render: (r) => n1(r.level100) },
      { label: 'Consistency', num: true, render: (r) => pct1(r.consistency_pct) }, { label: 'Pressure n', num: true, render: (r) => n0(r.pressure_deliveries) }, { label: 'Confidence', render: (r) => confBadge(r.sample_confidence) }, { label: 'P(top 10)', num: true, render: (r) => frac(r.p_top10) }] }))}`;
  }
  return html`<p class="lead">Compare up to six ranked players on overall evidence, pressure performance, consistency, uncertainty and phase splits.</p>
  <div class="controls"><span role="group" aria-label="Role"><a class="btn${bat ? ' primary' : ''}" href="#/compare?role=bat">Batters</a> <a class="btn${bat ? '' : ' primary'}" href="#/compare?role=bowl">Bowlers</a></span>
  <label>Add player <select id="cmp-add"><option value="">Select a player</option>${options}</select></label></div>
  <p class="chips" aria-label="Selected players">${sel.length ? sel.map((p) => html`<span class="chip">${p.player} <button class="chip-x" data-remove="${p.player_id}" aria-label="Remove ${p.player}">Ã—</button></span>`) : html`<span class="muted">No players selected</span>`}</p>${results}`;
}
export function mount(root, data, ctx) {
  const go = (ids) => ctx.navigate({ role: data.role, ids: ids.join(',') });
  root.querySelector('#cmp-add')?.addEventListener('change', (e) => { if (e.target.value && data.ids.length < 6) go([...data.ids, Number(e.target.value)]); });
  root.addEventListener('click', (e) => { const r = e.target.closest('[data-remove]'); if (r) go(data.ids.filter((i) => i !== Number(r.dataset.remove))); });
}



