// Safe templating + formatting helpers (no DOM access at import time, so they are unit-testable in Node).
export class Raw { constructor(s) { this.s = String(s); } toString() { return this.s; } }
export const raw = (s) => new Raw(s);
export function esc(v) {
  if (v === null || v === undefined) return '';
  if (v instanceof Raw) return v.s;
  if (Array.isArray(v)) return v.map(esc).join('');
  return String(v).replace(/[&<>"'`]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;' }[c]));
}
/** Tagged template: every interpolation is HTML-escaped unless wrapped in raw() or produced by another html`` call. */
export function html(strings, ...vals) {
  let out = '';
  strings.forEach((s, i) => { out += s; if (i < vals.length) out += esc(vals[i]); });
  return new Raw(out);
}
export const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
export const n0 = (v) => (isNum(v) ? Math.round(v).toLocaleString('en-US') : '–');
export const n1 = (v) => (isNum(v) ? v.toFixed(1) : '–');
export const n2 = (v) => (isNum(v) ? v.toFixed(2) : '–');
export const n3 = (v) => (isNum(v) ? v.toFixed(3) : '–');
export const pct0 = (v) => (isNum(v) ? `${Math.round(v)}%` : '–');
export const pct1 = (v) => (isNum(v) ? `${v.toFixed(1)}%` : '–');
export const frac = (v) => (isNum(v) ? `${Math.round(v * 100)}%` : '–');
export const signed1 = (v) => (isNum(v) ? `${v > 0 ? '+' : ''}${v.toFixed(1)}` : '–');
export const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
export const tierLetter = (t) => (t ? String(t)[0] : '–');
export function qs(params) {
  const p = Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== '');
  return p.length ? '?' + p.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&') : '';
}
export const slug = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
