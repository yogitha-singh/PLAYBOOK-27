import * as api from '../api.js';
import { html, raw, n0, n1, n2, signed1, frac, pct1 } from '../util.js';
import { table, pager, tierBadge, confBadge, playerCell, callout, evidenceNote, card, toast, openDialog } from '../components.js';
import { profileView } from './profile.js';
import { forest } from '../charts.js';

const ROLE_FILTERS = { bat: ['Opener', 'Number 3', 'Middle order', 'Finisher', 'Lower order'], bowl: ['Pace', 'Spin', 'powerplay', 'middle overs', 'death'] };
export async function openPlayer(id, role) {
  const det = await api.get(`/players/${id}`, { role });
  const d = det.profiles[role];
  const ex = d.status === 'Ranked' ? await api.get(`/players/${id}/explain`, { role }).catch(() => null) : null;   // decomposition exists for ranked players only
  return profileView(d, ex, role);
}
export async function addToShortlist(id, role, note = '') {
  try { await api.write('POST', '/scouting/shortlist', { player_id: Number(id), role, note }); toast('Added to shortlist', 'ok'); }
  catch (e) { toast(e.status === 409 ? 'Already on the shortlist' : e.status === 401 || e.status === 503 ? 'Shortlist writes need an API key — set it in the Auction Room.' : e.message, e.status === 409 ? 'info' : 'bad'); }
}

export function makeIntelligence(role) {
  const bat = role === 'bat', ep = bat ? '/batters/rankings' : '/bowlers/rankings';
  const meta = { path: bat ? 'batters' : 'bowlers', title: bat ? 'Batter Intelligence' : 'Bowler Intelligence', nav: bat ? 'Batters' : 'Bowlers' };
  const params = (q) => ({ status: q.status || 'ranked', q: q.q, tier: q.tier, role_inferred: q.role_inferred, sort_by: q.sort_by || 'rank', order: q.order || 'asc', page: q.page || 1, page_size: 25 });
  const load = async (ctx) => ({ res: await api.get(ep, params(ctx.query)), q: ctx.query });
  const cols = bat ? [
    { label: 'SR: pressure vs other', num: true, render: (r) => html`${n1(r.p_strike_rate)} <span class="muted">vs ${n1(r.b_strike_rate)}</span>`, title: 'Strike rate in pressure deliveries vs all other deliveries' },
    { label: 'Runs vs exp.', num: true, render: (r) => signed1(r.p_runs_above_exp), title: 'Runs above what an average batter scores in the same pressure situations (dismissals vs expected: see scouting card)' }]
    : [{ label: 'Econ: pressure vs other', num: true, render: (r) => html`${n2(r.p_economy)} <span class="muted">vs ${n2(r.b_economy)}</span>` },
      { label: 'Runs saved vs exp.', num: true, render: (r) => signed1(r.p_runs_saved_vs_exp), title: 'Wickets vs expected: see scouting card' }];
  function view({ res, q }) {
    const sort = { by: q.sort_by || 'rank', order: q.order || 'asc' };
    const columns = [{ label: 'Rank', sort: 'rank', render: (r) => r.rank ?? '–' }, { label: 'Player', sort: 'player', cls: 'player', render: playerCell },
      { label: 'Tier', render: (r) => (r.status === 'Ranked' ? tierBadge(r.tier) : html`<span class="muted small">${r.status.split(' (')[0]}</span>`) },
      { label: 'PRI (90% int.)', sort: 'PRI', num: true, render: (r) => (r.status === 'Ranked' ? html`<strong>${n1(r.PRI)}</strong> <span class="muted small">${n1(r.PRI_lo)}–${n1(r.PRI_hi)}</span>` : '–') },
      { label: 'Value /100', sort: 'level100', num: true, render: (r) => signed1(r.level100), title: 'Value /100 = shrunk value above expectation per 100 pressure deliveries' },
      { label: 'Consistency', sort: 'consistency_pct', num: true, render: (r) => pct1(r.consistency_pct) },
      ...cols, { label: 'Pressure n', sort: 'pressure_deliveries', render: (r) => html`${n0(r.pressure_deliveries)} ${confBadge(r.sample_confidence)}`, title: 'Pressure deliveries (statistical sample) and sample confidence' },
      { label: 'P(top 10)', sort: 'p_top10', num: true, render: (r) => frac(r.p_top10) }];
    const opt = (list, cur) => list.map((v) => html`<option value="${v}"${cur === v ? raw(' selected') : ''}>${v}</option>`);
    return html`<p class="lead">${bat ? 'Batters ranked by how much better than an average batter they perform in the same high-pressure situations.' : 'Bowlers ranked by how much better than an average bowler they perform in the same high-pressure situations.'} Select a name for the full scouting card.</p>
    <form class="filters" id="filters" aria-label="Filters"><label>Search<input type="search" name="q" value="${q.q || ''}" placeholder="Player name"></label>
    <label>Status<select name="status"><option value="ranked">Ranked</option><option value="low_confidence"${q.status === 'low_confidence' ? raw(' selected') : ''}>Low-confidence (not ranked)</option><option value="all"${q.status === 'all' ? raw(' selected') : ''}>All with pressure data</option></select></label>
    <label>Tier<select name="tier"><option value="">Any</option>${opt(['A', 'B', 'C'], q.tier)}</select></label>
    <label>Role (inferred)<select name="role_inferred"><option value="">Any</option>${opt(ROLE_FILTERS[role], q.role_inferred)}</select></label><button class="btn primary" type="submit">Apply</button> <button class="btn" type="button" data-action="reset">Reset</button></form>
    ${card(`${meta.nav} leaderboard`, html`${table({ caption: `${meta.title} leaderboard`, columns, rows: res.items, sort })}${pager(res)}`, { sub: 'Column headers sort. Pressure n = pressure deliveries used for the statistics.' })}${evidenceNote}`;
  }
  function mount(root, data, ctx) {
    const nav = (patch) => ctx.navigate({ ...ctx.query, ...patch });
    root.querySelector('#filters')?.addEventListener('submit', (e) => { e.preventDefault(); const f = Object.fromEntries(new FormData(e.target)); nav({ ...f, page: 1 }); });
    root.querySelector('[data-action=reset]')?.addEventListener('click', () => ctx.navigate({}));
    root.addEventListener('click', async (e) => {
      const s = e.target.closest('[data-sort]'); if (s) { const k = s.dataset.sort, cur = ctx.query.sort_by || 'rank'; nav({ sort_by: k, order: cur === k && (ctx.query.order || 'asc') === 'asc' && k !== 'rank' ? 'desc' : (cur === k ? 'asc' : (k === 'player' || k === 'rank' || k === 'sample_confidence' ? 'asc' : 'desc')), page: 1 }); return; }
      const p = e.target.closest('[data-page]'); if (p) { nav({ page: p.dataset.page }); return; }
      const pl = e.target.closest('[data-player]'); if (pl) { try { openDialog(await openPlayer(pl.dataset.player, role), { label: 'Scouting card' }); } catch (err) { toast(err.message, 'bad'); } }
    });
  }
  return { meta, load, view, mount };
}
export const batters = makeIntelligence('bat'), bowlers = makeIntelligence('bowl');
