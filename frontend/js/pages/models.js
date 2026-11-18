import * as api from '../api.js';
import { html, raw, n0, n3, esc } from '../util.js';
import { card, callout, table } from '../components.js';
import { bars, calibration } from '../charts.js';

export const meta = { path: 'models', title: 'Model Insights', nav: 'Model Insights' };
const NAMES = { x_runs: 'Expected runs (batting)', x_out: 'Dismissal probability', x_charged: 'Expected runs conceded (bowling)', x_bwk: 'Wicket probability (bowling)', wp: 'Win probability', lev: 'Leverage (|ΔWP| of next ball)' };
const KEY = { reg: ['MAE', 'RMSE', 'R2'], clf: ['ROC_AUC', 'PR_AUC', 'LogLoss', 'Brier', 'ECE'] };
export async function load(ctx) {
  const task = NAMES[ctx.query.task] ? ctx.query.task : 'wp';
  const [m, fi] = await Promise.all([api.get('/models/metrics'), api.get('/models/feature-importance', { task })]);
  return { m, fi, task };
}
export function view({ m, fi, task }) {
  const t = m.tasks[task], keys = KEY[t.kind];
  const rows = Object.entries(t.test_metrics).map(([k, v]) => ({ model: k.replaceAll('_', ' '), selected: k === t.selected_model, ...v }));
  return html`<p class="lead">Every number here is read from the stored training run (model v${m.model_version}) — nothing is typed in. ${m.caveat}.</p>
  <div class="controls"><label>Model <select id="mi-task">${Object.entries(NAMES).map(([k, v]) => html`<option value="${k}"${k === task ? raw(' selected') : ''}>${v}</option>`)}</select></label></div>
  <div class="grid-2">${card(`${NAMES[task]} — chronological test results`, html`${table({ caption: 'Test metrics by candidate model', rows, columns: [{ key: 'model', label: 'Model' }, { label: 'Chosen', render: (r) => (r.selected ? '✔ (on validation)' : '') }, ...keys.map((k) => ({ label: k.replace('_', '-'), num: true, render: (r) => n3(r[k]) }))] })}
    <p class="muted small">Train ${n0(t.n_train)} · validation ${n0(t.n_valid)} · test ${n0(t.n_test)} deliveries. Split: train ≤ ${m.split.train_end}, validation ≤ ${m.split.valid_end}, test after. Hyper-parameters and model family chosen on <strong>validation only</strong>; test reported once. Cross-fitted (out-of-fold, grouped by match) metrics: ${keys.map((k) => `${k.replace('_', '-')} ${n3(t.cv_oof_metrics[k])}`).join(' · ')}.</p>
    ${t.selection_override ? callout('info', 'Documented override', t.selection_override.reason) : ''}`, { sub: t.kind === 'reg' ? 'Regression baseline: predicting the mean (R² = 0).' : `Baseline: predicting the base rate (AUC = 0.5). Base rate ${n3(t.test_metrics.baseline_mean.base_rate)}.` })}
  ${card('Feature importance (permutation)', raw(bars(fi.items.slice(0, 10).map((i) => ({ label: i.feature, value: i.importance })), { label: `Permutation importance for ${NAMES[task]}`, fmt: (v) => v.toFixed(4) })), { sub: fi.method })}</div>
  ${t.test_calibration ? html`<div class="grid-2">${card('Calibration (test set)', raw(calibration(t.test_calibration, { label: `Calibration of ${NAMES[task]}` })), { sub: 'Points on the dashed line = predicted probabilities match observed frequencies.' })}
  ${card('Class imbalance handling', html`${table({ caption: 'Unweighted vs balanced class weights', rows: Object.entries(t.class_imbalance_comparison).map(([k, v]) => ({ k: k.replaceAll('_', ' '), ...v })), columns: [{ key: 'k', label: 'Training' }, { label: 'Brier', num: true, render: (r) => n3(r.Brier) }, { label: 'ECE', num: true, render: (r) => n3(r.ECE) }, { label: 'Recall@prev', num: true, render: (r) => n3(r['Recall@prev']) }, { label: 'PR-AUC', num: true, render: (r) => n3(r.PR_AUC) }] })}<p class="muted small">Balanced weighting distorts probabilities (calibration error explodes) without improving ranking, so unweighted, calibrated probabilities are used; evaluation relies on PR-AUC, log-loss, Brier and ECE rather than accuracy.</p>`)}</div>` : ''}
  ${callout('warn', 'Dataset & model limitations', 'Ball-level outcomes are mostly noise (R² ≈ 3%, AUC ≈ 0.6), so these models are context baselines, not predictors of individual deliveries. Win probability is trained on ~800 correlated matches and is slightly under-confident for outsiders in the last overs. Importance describes predictive association, not causation. SHAP was not available offline.')}`;
}
export function mount(root, data, ctx) { root.querySelector('#mi-task')?.addEventListener('change', (e) => ctx.navigate({ task: e.target.value })); }
