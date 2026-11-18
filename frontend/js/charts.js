// Dependency-free SVG charts. Pure functions returning SVG strings (accessible: role=img, aria-label, <title>, text labels).
import { esc, isNum, n1 } from './util.js';
export const narrow = () => (globalThis.innerWidth || 1200) < 640;
const C = { s: ['#EA1A85', '#0A1F44', '#5B6BA8', '#F29BC8', '#7B8299'], grid: '#E8EAF0', axis: '#565C79', text: '#20243A' };
const T = (s, x, y, o = {}) => `<text x="${x}" y="${y}" font-size="${o.size || 12}" fill="${o.fill || C.axis}" text-anchor="${o.anchor || 'start'}"${o.weight ? ` font-weight="${o.weight}"` : ''}${o.rot ? ` transform="rotate(${o.rot} ${x} ${y})"` : ''}>${esc(s)}</text>`;
const wrap = (w, h, label, body) => `<svg class="chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label)}" xmlns="http://www.w3.org/2000/svg"><title>${esc(label)}</title>${body}</svg>`;
const ticks = (lo, hi, n = 5) => { const st = (hi - lo) / n; return Array.from({ length: n + 1 }, (_, i) => lo + i * st); };
const nice = (lo, hi) => { if (lo === hi) { lo -= 1; hi += 1; } const pad = (hi - lo) * 0.08; return [lo - pad, hi + pad]; };

/** Forest plot: point + interval per row. rows: {label, value, lo, hi} */
export function forest(rows, { label = 'Estimates with 90% intervals', ref = 50, refLabel = 'league average', width = narrow() ? 360 : 640, rowH = 30, unit = '' } = {}) {
  const clean = rows.filter((r) => isNum(r.value));
  if (!clean.length) return '';
  const L = narrow() ? 128 : 190, R = 24, top = 22, h = top + clean.length * rowH + 34, pw = width - L - R;
  const [lo, hi] = nice(Math.min(...clean.map((r) => (isNum(r.lo) ? r.lo : r.value)), ref), Math.max(...clean.map((r) => (isNum(r.hi) ? r.hi : r.value)), ref));
  const x = (v) => L + ((v - lo) / (hi - lo)) * pw;
  let b = ticks(lo, hi).map((t) => `<line x1="${x(t)}" x2="${x(t)}" y1="${top - 6}" y2="${h - 26}" stroke="${C.grid}"/>${T(n1(t), x(t), h - 10, { anchor: 'middle' })}`).join('');
  b += `<line x1="${x(ref)}" x2="${x(ref)}" y1="${top - 8}" y2="${h - 26}" stroke="${C.s[1]}" stroke-dasharray="4 3"/>${T(`${refLabel} ${ref}`, x(ref), 12, { anchor: 'middle', fill: C.s[1] })}`;
  clean.forEach((r, i) => {
    const y = top + i * rowH + rowH / 2;
    b += T(r.label, L - 10, y + 4, { anchor: 'end', size: 12, fill: C.text });
    if (isNum(r.lo) && isNum(r.hi)) b += `<line x1="${x(r.lo)}" x2="${x(r.hi)}" y1="${y}" y2="${y}" stroke="${C.s[2]}" stroke-width="2.5" stroke-linecap="round"/><line x1="${x(r.lo)}" x2="${x(r.lo)}" y1="${y - 5}" y2="${y + 5}" stroke="${C.s[2]}" stroke-width="2"/><line x1="${x(r.hi)}" x2="${x(r.hi)}" y1="${y - 5}" y2="${y + 5}" stroke="${C.s[2]}" stroke-width="2"/>`;
    b += `<circle cx="${x(r.value)}" cy="${y}" r="5.5" fill="${C.s[0]}" stroke="#fff" stroke-width="1.5"><title>${esc(r.label)}: ${n1(r.value)}${unit}${isNum(r.lo) ? ` (${n1(r.lo)} to ${n1(r.hi)})` : ''}</title></circle>`;
  });
  return wrap(width, h, label, b);
}

/** Horizontal bars. items: {label, value, color?} */
export function bars(items, { label = 'Bar chart', width = narrow() ? 360 : 560, rowH = 28, fmt = n1 } = {}) {
  const it = items.filter((r) => isNum(r.value));
  if (!it.length) return '';
  const L = narrow() ? 150 : 190, R = 56, h = it.length * rowH + 16, pw = width - L - R;
  const lo = Math.min(0, ...it.map((r) => r.value)), hi = Math.max(0, ...it.map((r) => r.value)) || 1;
  const x = (v) => L + ((v - lo) / (hi - lo || 1)) * pw, x0 = x(0);
  let b = `<line x1="${x0}" x2="${x0}" y1="4" y2="${h - 8}" stroke="${C.axis}"/>`;
  it.forEach((r, i) => {
    const y = 8 + i * rowH, xv = x(r.value);
    b += T(r.label, L - 8, y + rowH / 2 + 1, { anchor: 'end', size: 12, fill: C.text });
    b += `<rect x="${Math.min(x0, xv)}" y="${y + 3}" width="${Math.max(1, Math.abs(xv - x0))}" height="${rowH - 10}" rx="3" fill="${r.color || C.s[r.value >= 0 ? 0 : 2]}"><title>${esc(r.label)}: ${fmt(r.value)}</title></rect>`;
    b += T(fmt(r.value), r.value >= 0 ? xv + 5 : x0 + 5, y + rowH / 2 + 1, { anchor: 'start', size: 11, fill: C.text });
  });
  return wrap(width, h, label, b);
}

/** Grouped vertical bars. series: [{name, values[]}] across categories[]. */
export function grouped(categories, series, { label = 'Grouped bars', width = narrow() ? 360 : 560, height = 260, fmt = n1, yLabel = '' } = {}) {
  const vals = series.flatMap((s) => s.values).filter(isNum);
  if (!vals.length) return '';
  const L = 48, R = 12, T0 = 16, B = 62, pw = width - L - R, ph = height - T0 - B;
  const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals) || 1, y = (v) => T0 + ph - ((v - lo) / (hi - lo || 1)) * ph;
  let b = ticks(lo, hi, 4).map((t) => `<line x1="${L}" x2="${width - R}" y1="${y(t)}" y2="${y(t)}" stroke="${C.grid}"/>${T(fmt(t), L - 6, y(t) + 4, { anchor: 'end' })}`).join('');
  const gw = pw / categories.length, bw = Math.min(34, (gw - 14) / series.length);
  categories.forEach((c, i) => {
    const gx = L + i * gw + (gw - bw * series.length) / 2;
    series.forEach((s, j) => { const v = s.values[i]; if (!isNum(v)) return; b += `<rect x="${gx + j * bw}" y="${Math.min(y(v), y(0))}" width="${bw - 2}" height="${Math.max(1, Math.abs(y(v) - y(0)))}" fill="${C.s[j % 5]}" rx="2"><title>${esc(s.name)} – ${esc(c)}: ${fmt(v)}</title></rect>`; });
    b += T(c, L + i * gw + gw / 2, height - B + 16, { anchor: 'middle', size: 11, fill: C.text });
  });
  b += series.map((s, j) => `<rect x="${L + j * 130}" y="${height - 22}" width="12" height="12" fill="${C.s[j % 5]}" rx="2"/>${T(s.name, L + j * 130 + 17, height - 12, { fill: C.text })}`).join('');
  if (yLabel) b += T(yLabel, 12, T0 + ph / 2, { anchor: 'middle', rot: -90 });
  return wrap(width, height, label, b);
}

/** Line chart. series: [{name, points:[{x,y}], dash?}] */
export function lines(series, { label = 'Line chart', width = narrow() ? 360 : 600, height = 280, xLabel = '', yLabel = '', fmt = n1, yMin } = {}) {
  const pts = series.flatMap((s) => s.points).filter((p) => isNum(p.x) && isNum(p.y));
  if (!pts.length) return '';
  const L = 52, R = 14, T0 = 14, B = 62, pw = width - L - R, ph = height - T0 - B;
  const xs = pts.map((p) => p.x), xlo = Math.min(...xs), xhi = Math.max(...xs);
  const ylo = isNum(yMin) ? yMin : Math.min(0, ...pts.map((p) => p.y));
  let yhi = Math.max(...pts.map((p) => p.y)) || 1;
  yhi += (yhi - ylo) * 0.06;
  const x = (v) => L + ((v - xlo) / (xhi - xlo || 1)) * pw, y = (v) => T0 + ph - ((v - ylo) / (yhi - ylo || 1)) * ph;
  let b = ticks(ylo, yhi, 4).map((t) => `<line x1="${L}" x2="${width - R}" y1="${y(t)}" y2="${y(t)}" stroke="${C.grid}"/>${T(fmt(t), L - 6, y(t) + 4, { anchor: 'end' })}`).join('');
  b += [...new Set(xs)].filter((_, i, a) => a.length <= 12 || i % Math.ceil(a.length / 10) === 0).map((v) => T(v, x(v), height - B + 16, { anchor: 'middle' })).join('');
  series.forEach((s, j) => {
    const p = s.points.filter((q) => isNum(q.y));
    b += `<polyline fill="none" stroke="${C.s[j % 5]}" stroke-width="2.4"${s.dash ? ' stroke-dasharray="6 4"' : ''} points="${p.map((q) => `${x(q.x).toFixed(1)},${y(q.y).toFixed(1)}`).join(' ')}"/>`;
    b += p.map((q) => `<circle cx="${x(q.x).toFixed(1)}" cy="${y(q.y).toFixed(1)}" r="3" fill="${C.s[j % 5]}"><title>${esc(s.name)}, ${esc(q.x)}: ${fmt(q.y)}</title></circle>`).join('');
  });
  b += series.map((s, j) => `<line x1="${L + j * 150}" x2="${L + j * 150 + 22}" y1="${height - 17}" y2="${height - 17}" stroke="${C.s[j % 5]}" stroke-width="3"${s.dash ? ' stroke-dasharray="6 4"' : ''}/>${T(s.name, L + j * 150 + 28, height - 13, { fill: C.text })}`).join('');
  if (xLabel) b += T(xLabel, L + pw / 2, height - B + 34, { anchor: 'middle' });
  if (yLabel) b += T(yLabel, 12, T0 + ph / 2, { anchor: 'middle', rot: -90 });
  return wrap(width, height, label, b);
}

/** Radar. axes: names[], series: [{name, values[0..1]}] */
export function radar(axes, series, { label = 'Radar chart', size = narrow() ? 300 : 340 } = {}) {
  const cx = size / 2, cy = size / 2 + 6, r = size / 2 - 52, n = axes.length;
  const pt = (i, v) => { const a = (-Math.PI / 2) + (2 * Math.PI * i) / n; return [cx + Math.cos(a) * r * v, cy + Math.sin(a) * r * v]; };
  let b = [0.25, 0.5, 0.75, 1].map((g) => `<polygon points="${axes.map((_, i) => pt(i, g).map((q) => q.toFixed(1)).join(',')).join(' ')}" fill="none" stroke="${C.grid}"/>`).join('');
  b += axes.map((a, i) => { const [x, y] = pt(i, 1.12); return `<line x1="${cx}" y1="${cy}" x2="${pt(i, 1)[0].toFixed(1)}" y2="${pt(i, 1)[1].toFixed(1)}" stroke="${C.grid}"/>${T(a, x, y + 4, { anchor: 'middle', fill: C.text })}`; }).join('');
  series.forEach((s, j) => { b += `<polygon points="${s.values.map((v, i) => pt(i, isNum(v) ? Math.min(1, Math.max(0, v)) : 0).map((q) => q.toFixed(1)).join(',')).join(' ')}" fill="${C.s[j % 5]}" fill-opacity=".14" stroke="${C.s[j % 5]}" stroke-width="2"${j % 2 ? ' stroke-dasharray="6 3"' : ''}><title>${esc(s.name)}</title></polygon>`; });
  b += series.map((s, j) => `<rect x="8" y="${size + 8 + j * 16}" width="11" height="11" fill="${C.s[j % 5]}" rx="2"/>${T(s.name, 25, size + 18 + j * 16, { fill: C.text })}`).join('');
  return wrap(size, size + 14 + series.length * 16, label, b);
}

/** 100%-stacked horizontal bars. rows: {label, parts:[{name, value}]} */
export function stacked(rows, { label = 'Composition', width = narrow() ? 360 : 560, rowH = 34 } = {}) {
  const L = 90, R = 10, pw = width - L - R, h = rows.length * rowH + 34, names = [...new Set(rows.flatMap((r) => r.parts.map((p) => p.name)))];
  let b = '';
  rows.forEach((r, i) => {
    const tot = r.parts.reduce((s, p) => s + (isNum(p.value) ? p.value : 0), 0) || 1; let x = L; const y = 6 + i * rowH;
    b += T(r.label, L - 8, y + 19, { anchor: 'end', size: 12, fill: C.text });
    r.parts.forEach((p) => { const w = (p.value / tot) * pw; const ni = names.indexOf(p.name) % 5; b += `<rect x="${x.toFixed(1)}" y="${y + 3}" width="${w.toFixed(1)}" height="${rowH - 8}" fill="${C.s[ni]}"><title>${esc(r.label)} – ${esc(p.name)}: ${n1(p.value)}%</title></rect>${w > 34 ? T(`${Math.round(p.value)}%`, x + w / 2, y + 19, { anchor: 'middle', fill: ni === 3 ? C.text : '#FFFFFF', size: 11, weight: 600 }) : ''}`; x += w; });
  });
  b += names.map((n, j) => `<rect x="${L + j * 110}" y="${h - 20}" width="12" height="12" rx="2" fill="${C.s[j % 5]}"/>${T(n, L + j * 110 + 17, h - 10, { fill: C.text })}`).join('');
  return wrap(width, h, label, b);
}

/** Reliability diagram: rows {mean_pred, obs_rate, n} */
export function calibration(rows, { label = 'Calibration', size = narrow() ? 290 : 300 } = {}) {
  if (!rows?.length) return '';
  const L = 44, B = 40, T0 = 10, R = 10, pw = size - L - R, ph = size - T0 - B, mx = Math.max(0.05, ...rows.flatMap((r) => [r.mean_pred, r.obs_rate])) * 1.08;
  const x = (v) => L + (v / mx) * pw, y = (v) => T0 + ph - (v / mx) * ph;
  let b = ticks(0, mx, 4).map((t) => `<line x1="${L}" x2="${size - R}" y1="${y(t)}" y2="${y(t)}" stroke="${C.grid}"/>${T(t.toFixed(2), L - 5, y(t) + 4, { anchor: 'end' })}${T(t.toFixed(2), x(t), size - B + 15, { anchor: 'middle' })}`).join('');
  b += `<line x1="${x(0)}" y1="${y(0)}" x2="${x(mx)}" y2="${y(mx)}" stroke="${C.s[1]}" stroke-dasharray="5 4"/>`;
  b += `<polyline fill="none" stroke="${C.s[0]}" stroke-width="2" points="${rows.map((r) => `${x(r.mean_pred).toFixed(1)},${y(r.obs_rate).toFixed(1)}`).join(' ')}"/>`;
  b += rows.map((r) => `<circle cx="${x(r.mean_pred).toFixed(1)}" cy="${y(r.obs_rate).toFixed(1)}" r="4" fill="${C.s[0]}"><title>predicted ${r.mean_pred.toFixed(3)}, observed ${r.obs_rate.toFixed(3)} (n=${r.n})</title></circle>`).join('');
  b += T('predicted probability', L + pw / 2, size - 6, { anchor: 'middle' }) + T('observed rate', 11, T0 + ph / 2, { anchor: 'middle', rot: -90 });
  return wrap(size, size, label, b);
}

/** Probability meter 0..1 */
export function meter(p, { label = 'Probability', width = 320 } = {}) {
  if (!isNum(p)) return '';
  const w = width - 20;
  return wrap(width, 44, `${label}: ${(p * 100).toFixed(0)}%`, `<rect x="10" y="10" width="${w}" height="16" rx="8" fill="${C.grid}"/><rect x="10" y="10" width="${(w * p).toFixed(1)}" height="16" rx="8" fill="${C.s[0]}"/><line x1="${10 + w / 2}" x2="${10 + w / 2}" y1="6" y2="30" stroke="${C.s[1]}" stroke-dasharray="3 2"/>${T('0%', 10, 42)}${T('50%', 10 + w / 2, 42, { anchor: 'middle' })}${T('100%', 10 + w, 42, { anchor: 'end' })}`);
}
