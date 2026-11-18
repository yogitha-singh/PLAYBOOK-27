// Reusable UI pieces. All return Raw HTML built with html`` (auto-escaped). DOM-touching helpers are only called from mount().
import { html, raw, esc, n0, n1, frac, tierLetter } from './util.js';

const TIER_TEXT = { A: 'Robust contender: top-20 rank, stays in the top 10 in a meaningful share of resamples AND alternative definitions', B: 'Plausible but assumption-sensitive: top-20 rank that depends on the pressure definition or weights', C: 'Ranked pool: eligible, outside the top 20' };
export const tierBadge = (t) => html`<span class="badge tier-${tierLetter(t)}" title="${TIER_TEXT[tierLetter(t)] || 'Not ranked'}">Tier ${tierLetter(t)}</span>`;
export const confBadge = (c) => html`<span class="badge conf-${String(c || 'Low').toLowerCase()}" title="Sample confidence: High = at least 2x the minimum pressure sample; Moderate = meets the minimum; Low = below it">${c || 'Low'} sample</span>`;
export const typeBadge = (kind) => html`<span class="badge type-${kind}">${kind === 'model' ? 'MODEL ESTIMATE' : 'HISTORICAL OBSERVATION'}</span>`;

export const kpi = ({ label, value, sub = '', tone = '' }) => html`<div class="kpi ${tone}"><div class="kpi-label">${label}</div><div class="kpi-value">${value}</div>${sub ? html`<div class="kpi-sub">${sub}</div>` : ''}</div>`;
export const card = (title, body, { sub = '', id = '', cls = '', actions = '' } = {}) => html`<section class="card ${cls}"${id ? raw(` id="${esc(id)}"`) : ''}><header class="card-h"><div><h2>${title}</h2>${sub ? html`<p class="muted">${sub}</p>` : ''}</div>${actions}</header><div class="card-b">${body}</div></section>`;
export const callout = (kind, title, text) => html`<div class="callout ${kind}" role="note"><strong>${title}</strong><p>${text}</p></div>`;
export const empty = (msg) => html`<div class="empty"><p>${msg}</p></div>`;
export const skeleton = () => html`<div class="skeleton" aria-busy="true" aria-live="polite"><span class="sr-only">Loading…</span><div class="sk sk-h"></div><div class="sk-grid"><div class="sk"></div><div class="sk"></div><div class="sk"></div></div><div class="sk sk-b"></div></div>`;
export const errorBox = (e) => html`<div class="callout bad" role="alert"><strong>Something went wrong</strong><p>${e?.message || 'Unexpected error'}${e?.status ? ` (HTTP ${e.status}${e.code ? `, ${e.code}` : ''})` : ''}</p><p><button class="btn" data-action="retry">Try again</button></p></div>`;

/** Sortable responsive table. columns: [{key,label,sort?,num?,render?(row)->Raw|string,title?}] */
export function table({ caption, columns, rows, sort = {}, rowKey = null, rowAttr = null }) {
  if (!rows.length) return empty('No rows match the current filters.');
  const th = columns.map((c) => {
    const active = sort.by && c.sort === sort.by;
    const aria = c.sort ? (active ? (sort.order === 'asc' ? 'ascending' : 'descending') : 'none') : null;
    return html`<th scope="col" class="${c.num ? 'num' : ''}"${aria ? raw(` aria-sort="${aria}"`) : ''}${c.title ? raw(` title="${esc(c.title)}"`) : ''}>${c.sort ? html`<button class="th-btn" data-sort="${c.sort}">${c.label}<span aria-hidden="true">${active ? (sort.order === 'asc' ? ' ▲' : ' ▼') : ''}</span></button>` : c.label}</th>`;
  });
  const body = rows.map((r) => html`<tr${rowAttr ? raw(' ' + rowAttr(r)) : ''}>${columns.map((c) => html`<td class="${c.num ? 'num' : ''}${c.cls ? ' ' + c.cls : ''}">${c.render ? c.render(r) : (r[c.key] ?? '–')}</td>`)}</tr>`);
  return html`<div class="table-wrap" tabindex="0" role="region" aria-label="${caption}"><table><caption class="sr-only">${caption}</caption><thead><tr>${th}</tr></thead><tbody>${body}</tbody></table></div>`;
}

export function pager({ total, page, page_size }) {
  const pages = Math.max(1, Math.ceil(total / page_size));
  if (pages <= 1) return html`<p class="muted small">${n0(total)} result${total === 1 ? '' : 's'}</p>`;
  return html`<nav class="pager" aria-label="Pagination"><span class="muted small">${n0(total)} results · page ${page} of ${pages}</span><span><button class="btn" data-page="${page - 1}"${page <= 1 ? raw(' disabled') : ''}>Previous</button> <button class="btn" data-page="${page + 1}"${page >= pages ? raw(' disabled') : ''}>Next</button></span></nav>`;
}

export const playerCell = (r) => html`<button class="link-btn" data-player="${r.player_id}" aria-label="Open scouting card for ${r.player}">${r.player}</button><div class="muted small">${r.role_inferred || ''}${r.latest_team_ipl ? ' · ' + r.latest_team_ipl : r.latest_team_t20i ? ' · ' + r.latest_team_t20i : ''}</div>`;
export const evidenceNote = html`<p class="muted small">Pressure-specific performance is only <strong>weakly persistent</strong> in this data (split-half reliability ≈0.2–0.3). Treat ranks as evidence with uncertainty: prefer tiers, intervals and P(top 10) over small score gaps.</p>`;

// ---------- DOM helpers (browser only; never called at import time) ----------
export function toast(msg, kind = 'info') {
  const host = document.getElementById('toasts'); if (!host) return;
  const t = document.createElement('div'); t.className = `toast ${kind}`; t.textContent = msg; host.appendChild(t);
  setTimeout(() => t.remove(), kind === 'bad' ? 7000 : 3800);
}
export function openDialog(contentHtml, { label = 'Details' } = {}) {
  const d = document.getElementById('dialog'); d.querySelector('.dialog-body').innerHTML = String(contentHtml); d.setAttribute('aria-label', label);
  if (!d.open) d.showModal(); d.querySelector('.dialog-body').scrollTop = 0; return d;
}
export const closeDialog = () => document.getElementById('dialog')?.close();
