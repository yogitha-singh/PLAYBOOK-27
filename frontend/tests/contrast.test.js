import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const css = readFileSync(new URL('../css/tokens.css', import.meta.url), 'utf8');
const tok = Object.fromEntries([...css.matchAll(/--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})/g)].map((m) => [m[1], m[2]]));
const lum = (h) => { const c = [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
test('text colours meet WCAG AA (4.5:1) on every surface they are used on', () => {
  for (const fg of ['text', 'muted', 'navy', 'pink-ink', 'ok', 'warn', 'bad', 'info']) for (const bg of ['white', 'bg', 'pink-soft']) {
    assert.ok(ratio(tok[fg], tok[bg]) >= 4.5, `${fg} on ${bg} = ${ratio(tok[fg], tok[bg]).toFixed(2)}`);
  }
  for (const fg of ['text', 'navy']) assert.ok(ratio(tok[fg], tok.grey) >= 4.5, `${fg} on grey`);
});
test('white text on navy / pink-ink buttons meets AA', () => {
  assert.ok(ratio('#FFFFFF', tok.navy) >= 4.5); assert.ok(ratio('#FFFFFF', tok['pink-ink']) >= 4.5);
});
test('brand pink is graphics-only: >=3:1 for non-text, never used for small text', () => {
  const r = ratio(tok.pink, tok.white); console.log(`# brand pink on white = ${r.toFixed(2)}:1`); assert.ok(r >= 3);
});
