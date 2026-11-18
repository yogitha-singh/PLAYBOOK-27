import test from 'node:test';
import assert from 'node:assert/strict';
import { parseHash, PAGES } from '../js/app.js';

test('hash router parses path and query, defaults to the Command Centre', () => {
  assert.deepEqual(parseHash('#/compare?role=bowl&ids=1,2'), { path: 'compare', query: { role: 'bowl', ids: '1,2' } });
  assert.deepEqual(parseHash(''), { path: 'overview', query: {} }); assert.deepEqual(parseHash('#/'), { path: 'overview', query: {} });
  assert.equal(parseHash('#/scenario?innings=2&runs_required=12').query.runs_required, '12');
});
test('all ten modules are registered with unique paths and complete contracts', () => {
  assert.equal(PAGES.length, 10); assert.equal(new Set(PAGES.map((p) => p.meta.path)).size, 10);
  for (const p of PAGES) { assert.equal(typeof p.load, 'function', p.meta.path); assert.equal(typeof p.view, 'function', p.meta.path); assert.ok(p.meta.title && p.meta.nav); }
});
