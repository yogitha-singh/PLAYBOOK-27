import * as api from '../api.js';
import { html, n0, n3 } from '../util.js';
import { card, table } from '../components.js';

export const meta = { path: 'status', title: 'Data & Model Status', nav: 'Data & Model Status' };

export async function load() {
  const [overview, metrics] = await Promise.all([api.get('/overview'), api.get('/models/metrics')]);
  return { ov: overview, m: metrics };
}

export function view({ ov, m }) {
  return html`<p class="lead">Live status of the analysis pipeline and model suite.</p>
  ${card('Dataset coverage', html`<ul class="plain">
    <li>Matches analysed: ${n0(ov.matches_analysed)}</li>
    <li>Deliveries analysed: ${n0(ov.deliveries_analysed)}</li>
    <li>Pressure deliveries: ${n0(ov.pressure_deliveries)}</li>
  </ul>`)}
  ${card('Pipeline', html`<p>Pipeline v${ov.model_status.pipeline_version} / Model v${ov.model_status.model_version}</p>`)}
  `;
}
