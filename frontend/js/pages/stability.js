import * as api from '../api.js';
import { html, n2 } from '../util.js';
import { card, table, callout } from '../components.js';

export const meta = { path: 'stability', title: 'Ranking Stability', nav: 'Ranking Stability' };

export async function load() {
  const val = await api.get('/methodology/validation');
  return { val };
}

export function view({ val }) {
  const sb = Object.fromEntries(val.split_half.batters.map(r => [r.measure, r.spearman_brown_full]));
  const sw = Object.fromEntries(val.split_half.bowlers.map(r => [r.measure, r.spearman_brown_full]));
  const tbat = (val.temporal?.batters || []).filter(t => t.spearman_with_late_pressure_value);
  const tbowl = (val.temporal?.bowlers || []).filter(t => t.spearman_with_late_pressure_value);

  return html`<p class="lead">How stable are these rankings? We test repeatability three ways: split-half reliability, chronological validation on later matches, and a 255-configuration sensitivity grid.</p>

  ${callout('warn', 'Read before trusting the order', 'Batter rankings have WEAK repeatability. Bowler rankings have MODEST repeatability. Use tiers and intervals, not decimal-point gaps.')}

  ${card('Split-half reliability', table({
    caption: 'How consistent are rankings in two random halves of matches?',
    rows: [
      { m: 'Level', b: sb.level, w: sw.level },
      { m: 'Consistency', b: sb.cons, w: sw.cons },
      { m: 'Delta (zero weight)', b: sb.delta, w: sw.delta },
      { m: 'Composite PRI', b: sb.composite, w: sw.composite }
    ],
    columns: [
      { key: 'm', label: 'Measure' },
      { label: 'Batters', num: true, render: r => n2(r.b) },
      { label: 'Bowlers', num: true, render: r => n2(r.w) }
    ]
  }), { sub: '1.0 = perfectly stable; near 0 = noise' })}

  ${card('Chronological validation', html`<p>We rank on matches up to a cutoff, then test whether that ranking predicts value in LATER matches.</p>`)}
  ${card('Sensitivity grid', html`<p>Every player is re-ranked under 255 alternative specifications. The share_top10 column in the Reliability Leaderboard shows how often they remain top-10.</p>`)}
  `;
}
