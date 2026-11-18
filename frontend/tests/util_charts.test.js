import test from 'node:test';
import assert from 'node:assert/strict';
import { esc, html, raw, qs, n1, n0, frac, signed1 } from '../js/util.js';
import * as ch from '../js/charts.js';
import { wellFormed } from './helpers.js';

test('html`` escapes interpolations, honours raw(), nests', () => {
  const evil = '<img src=x onerror=alert(1)>"\'';
  const out = String(html`<p title="${evil}">${evil}</p>`);
  assert.ok(!out.includes('<img') && !out.includes('onerror=alert') === false || !/<img/.test(out));
  assert.match(out, /&lt;img/); assert.equal(String(html`<b>${raw('<i>ok</i>')}</b>`), '<b><i>ok</i></b>');
  assert.equal(String(html`${[html`<a>${'<'}</a>`, 'x&y']}`), '<a>&lt;</a>x&amp;y');
  assert.equal(esc(null), ''); assert.equal(esc(0), '0');
});
test('formatters degrade gracefully on null/NaN', () => {
  assert.equal(n1(null), '–'); assert.equal(n1(NaN), '–'); assert.equal(n0(1234.6), '1,235'); assert.equal(frac(0.256), '26%'); assert.equal(signed1(2.34), '+2.3'); assert.equal(qs({ a: 1, b: '', c: 'x y' }), '?a=1&c=x%20y');
});
const rows = [{ label: 'A <b>', value: 55, lo: 50, hi: 61 }, { label: 'B', value: 52, lo: 45, hi: 58 }];
test('every chart produces well-formed SVG, with accessible names, and escapes labels', () => {
  const charts = [ch.forest(rows), ch.bars([{ label: 'x<y', value: -2 }, { label: 'z', value: 3 }]), ch.grouped(['a', 'b'], [{ name: 'S1', values: [1, 2] }, { name: 'S2', values: [3, null] }]),
    ch.lines([{ name: 'L', points: [{ x: 1, y: 1 }, { x: 2, y: 3 }] }, { name: 'M', dash: true, points: [{ x: 1, y: 2 }, { x: 2, y: 1 }] }]), ch.radar(['a', 'b', 'c'], [{ name: 'P', values: [0.2, 0.9, 0.5] }]),
    ch.stacked([{ label: 'Low', parts: [{ name: 'PP', value: 40 }, { name: 'Mid', value: 60 }] }]), ch.calibration([{ mean_pred: 0.1, obs_rate: 0.12, n: 50 }, { mean_pred: 0.3, obs_rate: 0.28, n: 50 }]), ch.meter(0.42)];
  for (const s of charts) { assert.ok(s.startsWith('<svg'), s.slice(0, 40)); assert.equal(wellFormed(s), null); assert.match(s, /role="img" aria-label="[^"]+"/); assert.ok(!s.includes('<b>') && !s.includes('x<y')); }
});
test('charts return empty string (not broken SVG) for empty / all-NaN data and survive single points', () => {
  assert.equal(ch.forest([]), ''); assert.equal(ch.bars([{ label: 'a', value: NaN }]), ''); assert.equal(ch.lines([{ name: 'x', points: [] }]), ''); assert.equal(ch.grouped(['a'], [{ name: 's', values: [null] }]), ''); assert.equal(ch.calibration([]), ''); assert.equal(ch.meter(null), '');
  for (const s of [ch.forest([{ label: 'one', value: 5 }]), ch.lines([{ name: 'x', points: [{ x: 1, y: 1 }] }]), ch.bars([{ label: 'z', value: 0 }]), ch.radar(['a', 'b', 'c'], [{ name: 'n', values: [null, 1, 2] }])]) { assert.equal(wellFormed(s), null); assert.ok(!/NaN|undefined|Infinity/.test(s), 'NaN/undefined leaked into SVG'); }
});
